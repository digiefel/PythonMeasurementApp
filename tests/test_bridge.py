"""Exercise the production executor with fake sessions in real subprocesses.

These checks cover transport/ownership, not hardware output behavior. On the lab
stack, verify reconnects, complete data counts, Abort for SMU and WGFMU, Skip before
queue continuation, and closing idle/active sessions. Preserve log.txt on failure
and check outputs on the instrument; the GUI becoming idle is not verification.
"""

import concurrent.futures
import json
import logging
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from instrumentio import bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        handler = logging.NullHandler()
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / "calls.jsonl"
        self.addCleanup(patch.stopall)
        patch.object(bridge, "_worker_command", return_value=[sys.executable, "-u", "-m", "tests.fake_worker"]).start()
        patch.object(bridge.RemoteB1500Session, "STOP_TIMEOUT_S", 0.3).start()
        self.emergency = patch.object(
            bridge.RemoteB1500Session, "_emergency_shutdown",
            side_effect=RuntimeError("Simulated emergency shutdown failure"),
        ).start()

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

    def test_configuration_sequences_cannot_be_interleaved_by_probes(self):
        session = self.connect()
        entered = threading.Event()
        release = threading.Event()
        def configure():
            with session.exclusive():
                session.echo("configure start")
                entered.set()
                release.wait(timeout=2)
                session.echo("configure end")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            config = executor.submit(configure)
            self.assertTrue(entered.wait(timeout=2))
            probe = executor.submit(session.echo, "probe")
            release.set()
            config.result(timeout=2)
            probe.result(timeout=2)
        self.assertEqual(self.history()[-3:], ["configure start", "configure end", "probe"])

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

    def test_cancel_hung_driver_reports_emergency_failure(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, 10)
            self.wait_for_call("slow_started")
            with self.assertRaisesRegex(bridge.InstrumentError, "Simulated emergency shutdown failure"):
                session.cancel()
            with self.assertRaises(bridge.InstrumentError):
                call.result(timeout=2)
        self.assertIsNotNone(session._process.poll())

    def test_hung_call_is_killed_before_emergency_reset_and_skip_is_preserved(self):
        session = self.connect()
        def reset():
            self.assertIsNotNone(session._process.poll())
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                bridge.InstrumentLease(session.address)
        self.emergency.side_effect = reset
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, 10, _timeout_s=None)
            self.wait_for_call("slow_started")
            session.cancel()
            with self.assertRaises(bridge.InstrumentCancelled):
                call.result(timeout=2)
        self.emergency.assert_called_once()
        self.assertNotIn("slow_finished", self.history())
        self.assertFalse(session.is_open)
        bridge.InstrumentLease(session.address).close()

    def test_explicit_timeout_resets_hardware_but_still_reports_timeout(self):
        session = self.connect()
        self.emergency.side_effect = None
        with self.assertRaisesRegex(bridge.InstrumentError, "did not respond"):
            session.slow(10, _timeout_s=.01)
        self.emergency.assert_called_once()

    def test_successful_normal_cleanup_does_not_need_emergency_reset(self):
        session = self.connect()
        session.cancel()
        self.emergency.assert_not_called()

    def test_pending_io_returns_before_owner_cleanup_without_emergency_reset(self):
        session = self.connect(interruptible=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, 10, _timeout_s=None)
            self.wait_for_call("slow_started")
            session.cancel()
            with self.assertRaises(bridge.InstrumentCancelled):
                call.result(timeout=2)
        self.emergency.assert_not_called()
        history = self.history()
        self.assertLess(history.index("io_returned_after_interrupt"), history.index("close"))
        self.assertEqual(history.count("close"), 1)

    def test_failed_shutdown_cannot_turn_into_successful_cancellation(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, 10)
            self.wait_for_call("slow_started")
            with self.assertRaises(bridge.InstrumentError):
                session.cancel()
            with self.assertRaises(bridge.InstrumentError) as caught:
                call.result(timeout=2)
            self.assertNotIsInstance(caught.exception, bridge.InstrumentCancelled)

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

    def test_cleanup_hang_is_bounded_after_a_command_failure(self):
        with patch.object(bridge, "_worker_command", return_value=[sys.executable, "-u", "-c",
                "from instrumentio import bridge_worker; bridge_worker.STOP_TIMEOUT_S=.2; import tests.fake_worker"]):
            session = self.connect(close_delay=10)
        start = time.monotonic()
        with self.assertRaises(bridge.InstrumentError):
            session.fail()
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertIsNotNone(session._process.poll())

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

    def test_existing_stream_signature_and_timeout_are_preserved(self):
        session = self.connect()
        seen = []
        session.stream_cv_sweep(1, 2, 0., 3, lambda *point: seen.append(point), timeout_s=1)
        self.assertEqual(seen, [(i, 1., 2., 3., 4., 5, 6) for i in range(3)])

    def test_invalid_timeout_is_rejected_before_execution(self):
        session = self.connect()
        for timeout in (-1, 0, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                session.echo("invalid deadline", _timeout_s=timeout)
        self.assertNotIn("invalid deadline", self.history())
        self.assertTrue(session.is_open)

    def test_default_wait_has_no_measurement_deadline(self):
        session = self.connect()
        self.assertIsNone(bridge.RemoteB1500Session.DEFAULT_TIMEOUT_S)
        session.timeout_s = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, .15)
            self.wait_for_call("slow_started")
            now = time.monotonic
            # Passing an hour must not change the outcome of a silent call.
            with patch.object(bridge.time, "monotonic", side_effect=lambda: now() + 3600):
                call.result(timeout=2)
        self.assertEqual(session.echo("still connected"), "still connected")

    def test_explicit_unbounded_wait_can_still_be_cancelled(self):
        session = self.connect()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(session.slow, .15, _timeout_s=None)
            self.wait_for_call("slow_started")
            session.cancel()
            with self.assertRaises(bridge.InstrumentCancelled):
                call.result(timeout=2)

    def test_cancellation_interrupts_connection_startup(self):
        stop = threading.Event()
        address = json.dumps(dict(record=str(self.record), connect_delay=10))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            call = executor.submit(bridge.RemoteB1500Session, address, cancel_events=(stop,))
            deadline = time.monotonic() + 2
            while not self.record.exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.005)
            stop.set()
            with self.assertRaises(bridge.InstrumentError):
                call.result(timeout=2)

    def test_parent_eof_bounds_even_a_blocked_native_operation(self):
        command = [sys.executable, "-u", "-c", "from instrumentio import bridge_worker; bridge_worker.STOP_TIMEOUT_S=.2; import tests.fake_worker"]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                process.stdin.write(json.dumps(["connect", json.dumps({"record": str(self.record)})]) + "\n")
                process.stdin.flush()
                self.assertEqual(json.loads(process.stdout.readline())[0], "result")
                process.stdin.write(json.dumps(["call", "", "slow", [10], {}]) + "\n")
                process.stdin.flush()
                self.wait_for_call("slow_started")
                process.stdin.close()
                self.assertEqual(process.wait(timeout=2), 1)
                self.assertIn("did not complete cancellation and device clear", process.stderr.read())
            finally:
                if process.poll() is None:
                    process.kill()
