import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from models import Device

# Exercise positioning without a SENTIO installation or connected instruments.
with patch.dict(sys.modules, {"prober": SimpleNamespace(ProberController=lambda log: Mock(prober=object()))}):
    import runner


class DevicePositioningTests(unittest.TestCase):
    def setUp(self):
        with patch.object(runner.atexit, "register"):
            self.runner = runner.MeasurementRunner(Mock())
        self.runner.prober_ctrl = Mock(prober=object(), subsite_origin=(0, 0))
        self.runner.log_callback = Mock()
        self.runner.CONTACT_LIGHTS_OFF_DELAY_S = 0

    def test_unknown_position_cannot_trigger_move_or_temperature_compensation(self):
        with self.assertRaisesRegex(ValueError, "Position unknown"):
            self.runner.move_to_device(Device("manual", None, None))
        self.runner.prober_ctrl.move_xy_home.assert_not_called()
        self.runner.prober_ctrl.get_temp.assert_not_called()

    def test_unknown_position_waits_for_confirmation_without_moving_or_contacting(self):
        device = Device("manual", None, None)
        self.runner.manual_position_callback = Mock(return_value=True)
        self.runner._prepare_for_measurement(device)
        self.runner.manual_position_callback.assert_called_once_with(device)
        self.runner.prober_ctrl.read_position.assert_not_called()
        self.runner.prober_ctrl.move_xy_home.assert_not_called()
        self.runner.prober_ctrl.contact.assert_not_called()

    def test_manual_confirmation_cancellation_aborts_queue(self):
        self.runner.manual_position_callback = Mock(return_value=False)
        self.runner.run_procedure = Mock(side_effect=lambda chip, site, subsite, device, proc, settings:
                                         self.runner._prepare_for_measurement(device))
        with self.assertRaises(runner.MeasurementAbortRequested):
            self.runner.run_devices("chip", None, None,
                                    [Device("first", None, None), Device("second", None, None)], None, {})
        self.assertEqual(self.runner.run_procedure.call_count, 1)

    def test_each_unknown_device_requires_confirmation(self):
        devices = [Device("first", None, None), Device("second", None, None)]
        self.runner.manual_position_callback = Mock(return_value=True)
        self.runner.run_procedure = Mock(side_effect=lambda chip, site, subsite, device, proc, settings:
                                         self.runner._prepare_for_measurement(device))
        self.runner.run_devices("chip", None, None, devices, None, {})
        self.assertEqual([call.args[0] for call in self.runner.manual_position_callback.call_args_list], devices)

    def test_missing_manual_callback_fails_before_hardware_movement(self):
        with self.assertRaisesRegex(RuntimeError, "confirmation is required"):
            self.runner._prepare_for_measurement(Device("manual", None, None))
        self.runner.prober_ctrl.move_xy_home.assert_not_called()

    def test_known_position_still_moves_and_contacts_automatically(self):
        self.runner.manual_position_callback = Mock()
        self.runner.prober_ctrl.read_position.return_value = (0, 0)
        self.runner.prober_ctrl.move_xy_home.return_value = (10, 20)
        self.runner.prober_ctrl.contact.return_value = True
        self.runner._prepare_for_measurement(Device("automatic", 10, 20))
        self.runner.manual_position_callback.assert_not_called()
        self.runner.prober_ctrl.move_xy_home.assert_called_once_with(10, 20)
        self.runner.prober_ctrl.contact.assert_called_once()
