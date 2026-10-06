"""Verify all device controls and actions consume the same ordered selection."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from models import Device, Site, Subsite
from tests.test_ui_connections import load_ui


class Value:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def __setitem__(self, key, value):
        setattr(self, key, value)


class DeviceSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_ui()

    def setUp(self):
        ui = self.module.MainUI.__new__(self.module.MainUI)
        self.ui = ui
        self.devices = [Device('B', 10, 20), Device('A', 30, 40), Device('C', 50, 60)]
        subsite = Subsite('sub', self.devices)
        ui.config = SimpleNamespace(sites=[Site('site', [subsite])], data={})
        ui._selected_devices = ()
        ui._selected_sites = tuple(ui.config.sites)
        ui.subsite_var = Value('sub')
        ui.site_cb = Value()
        ui.subsite_cb = Value()
        ui.device_cb = Value()
        for name in ('selected_devices_label', 'selected_sites_label', 'go_to_device_button', 'set_reference_button'):
            setattr(ui, name, Mock())
        for name, value in (
            ('proc_var', 'test'), ('set_home_var', False), ('auto_separation_var', True),
            ('chip_var', 'chip'), ('temp_comp_x_var', '0'), ('temp_comp_y_var', '0'), ('temp_comp_z_var', '0'),
        ):
            setattr(ui, name, Value(value))
        ui.procedure_classes = {'test': Mock()}
        ui.proc_cb = Mock()
        ui.render_param_form = Mock()
        ui.prober_available = False
        ui.runner = Mock()
        ui.root = Mock()
        ui.log = Mock()
        ui.temp_ui = Mock()
        ui.temp_ui.build_last_selection_fragment.return_value = {}
        ui._apply_temp_comp = Mock()

    def test_multi_selection_display_order_and_first_device_agree(self):
        self.ui._set_selected_devices({'A', 'B', 'missing'})
        self.assertEqual(self.ui.selected_device_names, ('B', 'A'))
        self.assertEqual(self.ui.device_cb.get(), 'B, A')
        self.assertIs(self.ui._first_selected_device(), self.devices[0])
        self.ui.go_to_device_button.configure.assert_called_with(text='Go To 1st Device')
        self.ui.set_reference_button.configure.assert_called_with(text='Set X,Y To 1st Device')

    def test_dropdown_replaces_multi_selection_with_one_device(self):
        self.ui._set_selected_devices({'B', 'A'})
        self.ui.device_cb.set('C')
        self.ui.on_device_selected()
        self.assertEqual(self.ui.selected_device_names, ('C',))
        self.ui.go_to_device_button.configure.assert_called_with(text='Go To Device')
        dialog = Mock()
        dialog.show.return_value = None
        with patch.object(self.module, 'DeviceSelectionDialog', return_value=dialog) as factory:
            self.ui.open_device_selection()
        self.assertEqual(factory.call_args.kwargs['initially_selected'], ('C',))
        self.assertEqual(self.ui.selected_device_names, ('C',))

    def test_dialog_updates_display_and_clearing_leaves_no_fallback_device(self):
        self.ui._set_selected_devices({'C'})
        dialog = Mock()
        dialog.show.return_value = {'B', 'A'}
        with patch.object(self.module, 'DeviceSelectionDialog', return_value=dialog):
            self.ui.open_device_selection()
            self.assertEqual(self.ui.device_cb.get(), 'B, A')
            dialog.show.return_value = set()
            self.ui.open_device_selection()
        self.assertEqual(self.ui.device_cb.get(), '')
        self.assertEqual(self.ui.selected_device_names, ())
        self.assertIsNone(self.ui._first_selected_device())

    def test_motion_and_alignment_use_first_displayed_device(self):
        self.ui._set_selected_devices({'A', 'B'})
        self.ui.prober_available = True
        self.ui.prober_go_to_device()
        self.ui.runner.move_to_device.assert_called_once_with(self.devices[0])
        self.ui.prober_set_reference()
        self.ui.runner.set_subsite_origin.assert_called_once_with(10, 20)

    def test_context_changes_remove_old_devices_and_empty_sites_clear_selection(self):
        self.ui._set_selected_devices({'A', 'B'})
        other = Device('D', 1, 2)
        self.ui.config.sites[0].subsites.append(Subsite('other', [other]))
        self.ui.subsite_var.set('other')
        self.ui.update_devices()
        self.assertEqual(self.ui.selected_device_names, ('D',))
        self.assertIs(self.ui._first_selected_device(), other)
        self.ui.config.sites = []
        self.ui.populate_sites()
        self.assertEqual(self.ui.device_cb.get(), '')
        self.assertEqual(self.ui.selected_device_names, ())

    def test_saved_multi_selection_overrides_old_independent_single_device(self):
        self.ui.apply_last_selection({'device': 'C', 'selected_devices': ['A', 'B']})
        saved = self.ui.build_last_selection()
        self.assertEqual(saved['device'], 'B')
        self.assertEqual(saved['selected_devices'], ['B', 'A'])
        self.assertEqual(self.ui.device_cb.get(), 'B, A')
        self.ui._set_selected_devices({'C'})
        self.ui.apply_last_selection(saved)
        self.assertEqual(self.ui.selected_device_names, ('B', 'A'))

    def test_legacy_single_and_empty_selections_restore_consistently(self):
        self.ui.apply_last_selection({'device': 'C', 'selected_devices': []})
        self.assertEqual(self.ui.selected_device_names, ('C',))
        self.ui._set_selected_devices(())
        saved = self.ui.build_last_selection()
        self.ui._set_selected_devices({'B'})
        self.ui.apply_last_selection(saved)
        self.assertEqual(self.ui.selected_device_names, ())
        self.assertEqual(self.ui.device_cb.get(), '')

    def test_run_queue_and_automatic_alignment_use_same_selection(self):
        ui = self.ui
        ui._set_selected_devices({'A', 'B'})
        ui._connection_busy = ui._closing = False
        ui._run_thread = None
        ui._b1500_available = Mock(return_value=True)
        ui.update_output_dir_from_ui = Mock(return_value=True)
        ui.collect_settings = Mock(return_value={})
        ui._validate_smu_channel_settings = Mock(return_value=True)
        ui._confirm_run_alignment = Mock(return_value=True)
        ui._set_running_state = Mock()
        ui._init_progress = Mock()
        ui._post = Mock()
        ui._post_log = Mock()
        ui.temp_ui.collect_run_inputs.return_value = (False, [], 0, 'Setpoint')
        ui.prober_available = True
        ui.set_home_var.set(True)
        with patch.object(self.module.threading, 'Thread',
                          side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            ui.run()
        self.assertEqual([entry[2] for entry in ui.runner.run_queue.call_args.args[1]], self.devices[:2])
        ui.runner.set_subsite_origin.assert_called_once_with(10, 20)
        self.assertIs(ui._confirm_run_alignment.call_args.args[2], self.devices[0])


if __name__ == '__main__':
    unittest.main()
