"""Connection lifecycle checks without GUI, plotting, or prober drivers."""

import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from instrumentio.bridge import InstrumentError


def load_ui():
    # Load the production UI while stubbing only optional presentation/drivers.
    optional_modules = {
        'tkinter': Mock(),
        'ui_temperature': SimpleNamespace(TemperatureUI=Mock()),
        'ui_device_selection': SimpleNamespace(DeviceSelectionDialog=Mock()),
        'ui_site_selection': SimpleNamespace(SiteSelectionDialog=Mock()),
        'ui_light_settings': SimpleNamespace(show_light_settings=Mock()),
        'tooltip_helper': SimpleNamespace(attach_tooltip=Mock()),
        'prober': SimpleNamespace(ProberController=Mock()),
        'plotting': SimpleNamespace(PlotBridge=Mock()),
    }
    with patch.dict(sys.modules, optional_modules):
        spec = importlib.util.spec_from_file_location(
            '_connection_test_ui', Path(__file__).resolve().parents[1] / 'ui.py',
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class UIConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_ui()

    def setUp(self):
        ui = self.module.MainUI.__new__(self.module.MainUI)
        self.ui = ui
        ui._closing = ui._connection_busy = ui._running = False
        ui.prober_available = True
        ui._selected_gpib_address = Mock(return_value='GPIB0::17::INSTR')
        ui.config = SimpleNamespace(data={'b1500': {'auto_discover_channels': False}})
        ui.prober_enabled_var = Mock()
        ui.prober_enabled_var.get.return_value = True
        ui.temp_ui = Mock()
        ui.temp_ui.enabled_var.get.return_value = True
        ui.root = Mock()
        ui.log = Mock()
        ui._refresh_connection_controls = Mock()
        ui._finish_prober_initialization = Mock()
        ui._set_contact_state = Mock()
        for name in ('light_settings_button', '_finish_btn', 'run_button', 'stop_frame', 'progress_frame'):
            setattr(ui, name, Mock())

        runner = self.module.MeasurementRunner.__new__(self.module.MeasurementRunner)
        ui.runner = runner
        runner.log = Mock()
        runner.stop_event = threading.Event()
        runner.skip_device_event = threading.Event()
        runner._b1500_lock = threading.Lock()
        runner.b1500 = Mock(address='GPIB0::17::INSTR', is_open=False)
        runner.temp_ref_c = 25.0
        runner.temp_comp_ref_z_heights = (1.0, 2.0)
        runner.prober_ctrl = Mock(prober=object(), subsite_origin=(100.0, 200.0))
        runner.prober_is_in_contact = Mock(return_value=False)
        runner.prober_ctrl.initialize.return_value = True

    def check_connections(self):
        self.ui._start_connection_check()
        self.ui._connection_thread.join(timeout=2)
        self.assertFalse(self.ui._connection_thread.is_alive())
        self.ui.root.after.call_args.args[1]()

    def test_reconnect_restores_b1500_and_preserves_alignment_and_temperature_reference(self):
        old = self.ui.runner.b1500
        new = Mock(address=old.address, is_open=True)
        with patch.dict(self.module.MeasurementRunner.get_b1500.__globals__, RemoteB1500Session=Mock(return_value=new)):
            self.check_connections()
        self.assertIs(self.ui.runner.b1500, new)
        old.cancel.assert_called_once()
        old.close.assert_not_called()
        self.ui.runner.prober_ctrl.initialize.assert_called_once_with()
        self.assertEqual(self.ui.runner.prober_ctrl.subsite_origin, (100.0, 200.0))
        self.assertEqual(self.ui.runner.temp_ref_c, 25.0)
        self.assertEqual(self.ui.runner.temp_comp_ref_z_heights, (1.0, 2.0))

    def test_connection_check_reuses_healthy_b1500(self):
        session = self.ui.runner.b1500
        session.is_open = True
        self.check_connections()
        self.assertIs(self.ui.runner.b1500, session)
        session.cancel.assert_not_called()
        session.close.assert_not_called()

    def test_new_prober_session_resets_temperature_reference(self):
        self.ui.runner.b1500.is_open = True
        self.ui.runner.prober_ctrl.prober = None
        self.check_connections()
        self.assertIsNone(self.ui.runner.temp_ref_c)
        self.assertIsNone(self.ui.runner.temp_comp_ref_z_heights)

    def test_failed_stop_cleanup_does_not_open_another_b1500_session(self):
        old = self.ui.runner.b1500
        old.cancel.side_effect = InstrumentError('Cleanup failed')
        factory = Mock()
        with patch.dict(self.module.MeasurementRunner.get_b1500.__globals__, RemoteB1500Session=factory):
            with self.assertLogs('_connection_test_ui', level='ERROR'):
                self.check_connections()
        factory.assert_not_called()
        self.assertIs(self.ui.runner.b1500, old)
        self.assertTrue(self.ui.runner.stop_event.is_set())
        self.assertEqual(self.ui.runner.prober_ctrl.subsite_origin, (100.0, 200.0))

    def test_end_of_run_restores_only_a_disconnected_session(self):
        self.ui._start_connection_check = Mock()
        self.ui._set_running_state(False)
        self.ui._start_connection_check.assert_called_once_with()
        self.ui._start_connection_check.reset_mock()
        self.ui.runner.b1500.is_open = True
        self.ui._set_running_state(False)
        self.ui._set_running_state(True)
        self.ui._start_connection_check.assert_not_called()

    def test_app_shutdown_does_not_start_a_connection_check(self):
        self.ui._closing = True
        self.ui._set_running_state(False)
        self.ui.root.after.assert_not_called()
        self.assertFalse(self.ui._connection_busy)


if __name__ == '__main__':
    unittest.main()
