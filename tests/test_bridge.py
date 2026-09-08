import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from instrumentio import bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / "calls.jsonl"
        self.addCleanup(patch.stopall)
        patch.object(bridge, "_worker_command", return_value=[sys.executable, "-u", "-m", "tests.fake_worker"]).start()
        patch.object(bridge.RemoteB1500Session, "STOP_TIMEOUT_S", 0.3).start()

    def connect(self, **options):
        session = bridge.RemoteB1500Session(json.dumps(dict(record=str(self.record), **options)), timeout_s=2)
        self.addCleanup(session.close)
        return session

    def history(self):
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def wait_for_call(self, value):
        deadline = time.monotonic() + 2
        while value not in self.history():
            if time.monotonic() >= deadline:
                self.fail(f"Call did not start: {value}")
            time.sleep(.005)

    def test_calls_and_subsession_share_interface(self):
        session = self.connect()
        self.assertEqual(session.echo({"value": 42}), {"value": 42})
        self.assertEqual(session.wgfmu.echo("subsession"), "subsession")
        self.assertTrue(session.bridge_info()["session_initialized"])

    def test_concurrent_calls_never_steal_responses(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(list(executor.map(session.echo, range(40))), list(range(40)))

    def test_callbacks_are_lossless_and_return_values(self):
        session = self.connect()
        seen = []
        def callback(index):
            seen.append(index)
            return index * 2
        self.assertEqual(session.samples(1000, callback), [i * 2 for i in range(1000)])
        self.assertEqual(seen, list(range(1000)))

    def test_callback_error_closes_instrument(self):
        session = self.connect()
        def callback(index):
            raise ValueError("Local callback failed")
        with self.assertRaisesRegex(ValueError, "Local callback failed"):
            session.samples(10, callback)
        self.assertEqual(self.history()[-1], "close")
        self.assertFalse(session.is_open)

    def test_reentrant_call_fails_without_deadlock(self):
        session = self.connect()
        with self.assertRaisesRegex(bridge.InstrumentError, "inside a data callback"):
            session.samples(1, lambda _: session.echo("nested"))
        self.assertNotIn("nested", self.history())

    def test_errors_retire_connection_and_preserve_diagnostics(self):
        session = self.connect()
        with self.assertLogs("instrumentio.bridge", level="ERROR") as logs:
            with self.assertRaises(bridge.InstrumentError):
                session.fail()
        self.assertIn("Simulated instrument failure", "\n".join(logs.output))
        with self.assertRaises(bridge.InstrumentError):
            session.echo("must not execute")
        self.assertNotIn("must not execute", self.history())
        self.assertEqual(self.history()[-1], "close")

    def test_timeout_prevents_late_and_queued_execution(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(session.slow, 10, _timeout_s=.1)
            self.wait_for_call("slow_started")
            second = executor.submit(session.echo, "queued")
            for future in (first, second):
                with self.assertRaises(bridge.InstrumentError):
                    future.result(timeout=3)
        self.assertNotIn("slow_finished", self.history())
        self.assertNotIn("queued", self.history())
        self.assertIsNotNone(session._process.poll())

    def test_cancel_does_not_wait_for_call_lock(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, .15)
            self.wait_for_call("slow_started")
            session.cancel()
            with self.assertRaises(bridge.InstrumentCancelled):
                call.result(timeout=2)
        self.assertEqual(self.history()[-1], "close")
        self.assertFalse(session.is_open)

    def test_cancel_hung_driver_reports_unknown_outputs(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, 10)
            self.wait_for_call("slow_started")
            with self.assertRaisesRegex(bridge.InstrumentError, "output state could not be confirmed"):
                session.cancel()
            with self.assertRaises(bridge.InstrumentError):
                call.result(timeout=2)
        self.assertIsNotNone(session._process.poll())

    def test_abrupt_exit_is_a_connection_failure(self):
        session = self.connect()
        with self.assertRaises(bridge.InstrumentError):
            session.crash()
        self.assertFalse(session.is_open)

    def test_bad_protocol_is_a_connection_failure(self):
        session = self.connect()
        with self.assertRaises(bridge.InstrumentError):
            session.corrupt()
        self.assertFalse(session.is_open)

    def test_driver_prints_do_not_corrupt_protocol(self):
        session = self.connect()
        with self.assertLogs("instrumentio.bridge", level="ERROR") as logs:
            self.assertEqual(session.noisy(), "åäö")
            session.close()
        self.assertIn("Vendor diagnostic: åäö", "\n".join(logs.output))

    def test_close_failure_is_not_reported_as_success(self):
        session = self.connect(close_error=True)
        with self.assertRaisesRegex(bridge.InstrumentError, "shutdown failed"):
            session.close()

    def test_close_is_idempotent_and_reaps_threads(self):
        session = self.connect()
        session.close()
        session.close()
        self.assertEqual(self.history().count("close"), 1)
        self.assertTrue(all(not thread.is_alive() for thread in session._threads))

    def test_invalid_arguments_do_not_damage_connection(self):
        session = self.connect()
        with self.assertRaises(TypeError):
            session.echo(object())
        self.assertEqual(session.echo("still usable"), "still usable")

    def test_failed_connect_keeps_process_details_out_of_user_error(self):
        with self.assertRaises(bridge.InstrumentError) as caught:
            self.connect(connect_error=True)
        self.assertNotIn("worker", str(caught.exception).lower())
        self.assertNotIn("Traceback", str(caught.exception))
