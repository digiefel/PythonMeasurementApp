import concurrent.futures
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

# These tests exercise runner ownership without a SENTIO installation.
with patch.dict(sys.modules, {"prober": SimpleNamespace(ProberController=lambda log: SimpleNamespace(prober=None))}):
    import runner


class RunnerConnectionTests(unittest.TestCase):
    def setUp(self):
        with patch.object(runner.atexit, "register"):
            self.runner = runner.MeasurementRunner(Mock())
        self.runner.log_callback = Mock()
        def connect(address, **kwargs):
            session = Mock(address=address, is_open=True)
            session.cancel.side_effect = lambda: setattr(session, "is_open", False)
            return session
        self.factory = patch.object(runner, "RemoteB1500Session", side_effect=connect).start()
        self.addCleanup(patch.stopall)

    def test_concurrent_connection_requests_create_one_session(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            sessions = list(executor.map(self.runner.get_b1500, ["address"] * 8))
        self.factory.assert_called_once()
        self.assertTrue(all(session is sessions[0] for session in sessions))

    def test_requested_run_replaces_failed_or_different_connection(self):
        first = self.runner.get_b1500("first")
        first.is_open = False
        second = self.runner.get_b1500("first")
        first.cancel.assert_called_once()
        self.assertIsNot(first, second)
        third = self.runner.get_b1500("other")
        second.cancel.assert_called_once()
        self.assertEqual(third.address, "other")

    def test_background_probes_cannot_open_or_reopen_connections(self):
        with self.assertRaises(runner.InstrumentError):
            self.runner.get_b1500("address", connect=False)
        self.factory.assert_not_called()
        session = self.runner.get_b1500("address")
        self.assertIs(self.runner.get_b1500("address", connect=False), session)
        session.is_open = False
        with self.assertRaises(runner.InstrumentError):
            self.runner.get_b1500("address", connect=False)
        self.factory.assert_called_once()

    def test_stop_and_skip_use_the_same_connection_cleanup(self):
        first = self.runner.get_b1500("address")
        self.runner.safe_stop()
        first.cancel.assert_called_once()
        with self.assertRaises(runner.MeasurementAbortRequested):
            self.runner.get_b1500("address")
        self.runner.stop_event.clear()
        second = self.runner.get_b1500("address")
        self.runner.safe_skip_device()
        second.cancel.assert_called_once()
        with self.assertRaises(runner.MeasurementSkipRequested):
            self.runner.get_b1500("address")

    def test_connection_cancellation_preserves_abort_and_skip_semantics(self):
        self.runner.config.data = {"output_dir": "unused"}
        for event, expected in ((self.runner.stop_event, runner.MeasurementAbortRequested),
                                (self.runner.skip_device_event, runner.MeasurementSkipRequested)):
            with self.subTest(expected=expected):
                session = self.runner.get_b1500("address")
                procedure = Mock()
                def execute(*args):
                    event.set()
                    raise runner.InstrumentCancelled("Measurement stopped")
                procedure.return_value.execute.side_effect = execute
                with self.assertRaises(expected):
                    self.runner.run_procedure("chip", SimpleNamespace(name="site"), SimpleNamespace(name="subsite"),
                                              SimpleNamespace(name="device"), procedure, {"gpib_address": "address"})
                event.clear()
