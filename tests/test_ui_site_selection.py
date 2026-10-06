"""Multi-site selection, partial queues, and site-map geometry without hardware."""

import importlib
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from models import Device, Site, Subsite
from tests.test_ui_connections import load_ui
from tests import test_ui_device_selection as device_tests


class SiteSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_ui()

    def setUp(self):
        device_tests.DeviceSelectionTests.setUp(self)
        self.other_devices = [Device('A', 1030, 40), Device('B', 1010, 20)]
        self.other_site = Site('other', [Subsite('sub', self.other_devices)])
        self.missing_subsite = Site('missing', [Subsite('different', [Device('B', 2000, 0)])])
        self.partial_site = Site('partial', [Subsite('sub', [Device('B', 3000, 0)])])
        self.ui.config.sites.extend([self.other_site, self.missing_subsite, self.partial_site])
        self.ui._set_selected_devices({'A', 'B'})

    def prepare_run(self, temperature=False):
        ui = self.ui
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
        ui.temp_ui.collect_run_inputs.return_value = (temperature, [25, 50], 0, 'Sweep')
        ui.prober_available = temperature
        return patch.object(self.module.threading, 'Thread',
                            side_effect=lambda target, daemon: SimpleNamespace(start=target))

    def test_site_field_dialog_and_dropdown_share_one_ordered_selection(self):
        self.ui._set_selected_sites({'other', 'site'})
        self.assertEqual(self.ui.site_cb.get(), 'site, other')
        self.assertEqual(self.ui.selected_site_names, ('site', 'other'))
        self.assertEqual(self.ui.selected_device_names, ('B', 'A'))
        dialog = Mock()
        dialog.show.return_value = None
        with patch.object(self.module, 'SiteSelectionDialog', return_value=dialog) as factory:
            self.ui.open_site_selection()
        self.assertEqual(factory.call_args.kwargs['initially_selected'], ('site', 'other'))
        self.ui.site_cb.set('other')
        self.ui.on_site_selected()
        self.assertEqual(self.ui.selected_site_names, ('other',))
        self.assertEqual(self.ui.device_cb.get(), 'A, B')
        self.ui.prober_available = True
        self.ui.prober_go_to_device()
        self.ui.runner.move_to_device.assert_called_once_with(self.other_devices[0])

    def test_dialog_updates_site_field_and_can_clear_selection(self):
        dialog = Mock()
        dialog.show.return_value = {'site', 'other'}
        with patch.object(self.module, 'SiteSelectionDialog', return_value=dialog):
            self.ui.open_site_selection()
            self.assertEqual(self.ui.site_cb.get(), 'site, other')
            dialog.show.return_value = set()
            self.ui.open_site_selection()
        self.assertEqual(self.ui.selected_site_names, ())
        self.assertEqual(self.ui.device_cb.get(), '')

    def test_queue_resolves_each_sites_own_devices_and_reports_partial_matches(self):
        self.ui._set_selected_sites({'site', 'other', 'missing', 'partial'})
        queue, missing = self.ui._build_measurement_queue()
        self.assertEqual([(site.name, sub.name, device.name) for site, sub, device in queue], [
            ('site', 'sub', 'B'), ('site', 'sub', 'A'),
            ('other', 'sub', 'B'), ('other', 'sub', 'A'), ('partial', 'sub', 'B'),
        ])
        self.assertIs(queue[2][2], self.other_devices[1])
        self.assertEqual(len(missing), 2)
        self.assertIn("subsite 'sub'", missing[0])
        self.assertIn("device 'A'", missing[1])

    def test_missing_first_site_preserves_requested_subsite_and_devices(self):
        self.ui._set_selected_sites({'other'})
        self.ui.config.sites.insert(0, self.ui.config.sites.pop(2))
        self.ui._set_selected_sites({'missing', 'other'})
        self.assertEqual(self.ui.subsite_var.get(), 'sub')
        self.assertEqual(set(self.ui.selected_device_names), {'A', 'B'})
        queue, missing = self.ui._build_measurement_queue()
        self.assertEqual(len(queue), 2)
        self.assertEqual(len(missing), 1)
        self.assertIs(self.ui._first_selected_device(), self.other_devices[0])

    def test_cancel_missing_starts_no_measurement(self):
        self.ui._set_selected_sites({'site', 'missing'})
        self.ui._confirm_skip_missing = Mock(return_value=False)
        with self.prepare_run():
            self.ui.run()
        self.ui._confirm_skip_missing.assert_called_once()
        self.ui.runner.run_queue.assert_not_called()
        self.ui.temp_ui.start_run.assert_not_called()
        self.ui._set_running_state.assert_not_called()

    def test_skip_missing_runs_only_available_entries_and_counts_entire_queue(self):
        self.ui._set_selected_sites({'site', 'other', 'missing', 'partial'})
        self.ui._confirm_skip_missing = Mock(return_value=True)
        with self.prepare_run():
            self.ui.run()
        queue = self.ui.runner.run_queue.call_args.args[1]
        self.assertEqual(len(queue), 5)
        self.ui._init_progress.assert_called_once_with(5)
        self.ui._confirm_skip_missing.assert_called_once()

    def test_temperature_run_receives_full_multi_site_queue(self):
        self.ui._set_selected_sites({'site', 'other'})
        with self.prepare_run(temperature=True):
            self.ui.run()
        queue = self.ui.runner.run_temperature_sweep.call_args.kwargs['measurement_queue']
        self.assertEqual(len(queue), 4)
        self.ui.temp_ui.start_run.assert_called_once_with([25, 50], 0, device_count=4)

    def test_saved_sites_roundtrip_and_empty_selection_has_no_hidden_site(self):
        self.ui._set_selected_sites({'site', 'other'})
        saved = self.ui.build_last_selection()
        self.assertEqual(saved['site'], 'site')
        self.assertEqual(saved['selected_sites'], ['site', 'other'])
        self.ui._set_selected_sites({'partial'})
        self.ui.apply_last_selection(saved)
        self.assertEqual(self.ui.site_cb.get(), 'site, other')
        self.assertEqual(self.ui.device_cb.get(), 'B, A')
        self.ui._set_selected_sites(())
        saved = self.ui.build_last_selection()
        self.ui._set_selected_sites({'site'})
        self.ui.apply_last_selection(saved)
        self.assertEqual(self.ui.selected_site_names, ())

    def test_missing_dialog_offers_cancel_and_skip_missing(self):
        for answer in ('Cancel', 'Skip missing'):
            commands = {}

            def button(*args, **kwargs):
                commands[kwargs['text']] = kwargs['command']
                return Mock()

            self.ui.root.wait_window.side_effect = lambda dialog: commands[answer]()
            with patch.object(self.module.ttk, 'Button', side_effect=button), patch.object(self.module, 'center_popup'):
                self.assertEqual(self.ui._confirm_skip_missing(['Missing/sub/device']), answer == 'Skip missing')
            self.assertEqual(set(commands), {'Cancel', 'Skip missing'})

    def runner(self):
        runner = self.module.MeasurementRunner.__new__(self.module.MeasurementRunner)
        runner.log = Mock()
        runner.run_procedure = Mock()
        runner.device_progress_cb = Mock()
        runner.temp_device_done_cb = Mock()
        runner.skip_device_event = threading.Event()
        runner.cancel_queue_event = threading.Event()
        runner.stop_event = threading.Event()
        runner._current_temp_step = None
        return runner

    def test_runner_visits_actual_contexts_with_global_progress_and_isolated_settings(self):
        self.ui._set_selected_sites({'site', 'other'})
        queue, _ = self.ui._build_measurement_queue()
        runner = self.runner()
        runner.run_procedure.side_effect = lambda chip, site, sub, dev, proc, settings: settings.update(local=dev.name)
        runner.run_queue('chip', queue, object, {'shared': 1})
        self.assertEqual([call.args[1:4] for call in runner.run_procedure.call_args_list], queue)
        self.assertEqual([call.args[:2] for call in runner.device_progress_cb.call_args_list],
                         [(1, 4), (2, 4), (3, 4), (4, 4)])
        self.assertEqual(len({id(call.args[-1]) for call in runner.run_procedure.call_args_list}), 4)

    def test_runner_finish_and_stop_applies_to_entire_site_queue_even_when_skipping(self):
        self.ui._set_selected_sites({'site', 'other'})
        queue, _ = self.ui._build_measurement_queue()
        runner = self.runner()

        def skip_and_finish(*args):
            runner.skip_device_event.set()
            runner.cancel_queue_event.set()
            raise self.module.MeasurementSkipRequested()

        runner.run_procedure.side_effect = skip_and_finish
        runner.run_queue('chip', queue, object, {})
        runner.run_procedure.assert_called_once()
        self.assertFalse(runner.skip_device_event.is_set())

    def test_existing_single_site_runner_uses_same_queue_path(self):
        runner = self.runner()
        site = self.ui.config.sites[0]
        subsite = site.subsites[0]
        runner.run_devices('chip', site, subsite, self.devices, object, {})
        self.assertEqual([call.args[1:4] for call in runner.run_procedure.call_args_list],
                         [(site, subsite, device) for device in self.devices])

    def test_runner_skip_continues_to_next_site_and_abort_stops_queue(self):
        self.ui._set_selected_sites({'site', 'other'})
        queue, _ = self.ui._build_measurement_queue()
        runner = self.runner()
        runner.run_procedure.side_effect = [self.module.MeasurementSkipRequested(), None, None, None]
        runner.run_queue('chip', queue, object, {})
        self.assertEqual(runner.run_procedure.call_count, 4)
        runner.run_procedure.reset_mock()
        runner.run_procedure.side_effect = self.module.MeasurementAbortRequested()
        with self.assertRaises(self.module.MeasurementAbortRequested):
            runner.run_queue('chip', queue, object, {})
        runner.run_procedure.assert_called_once()

    def test_runner_temperature_sweep_repeats_all_sites_at_each_temperature(self):
        self.ui._set_selected_sites({'site', 'other'})
        queue, _ = self.ui._build_measurement_queue()
        runner = self.runner()
        runner.is_prober_available = Mock(return_value=True)
        runner.prober_set_temp = Mock()
        runner.prober_wait_until_temp = Mock()
        runner.temp_step_started_cb = Mock()
        runner.temp_phase_cb = Mock()
        runner.run_temperature_sweep([25, 50], 0, 'chip', queue[0][0], queue[0][1], object, {},
                                     self.devices[:2], measurement_queue=queue)
        calls = runner.run_procedure.call_args_list
        self.assertEqual(len(calls), 8)
        self.assertEqual([call.args[1:4] for call in calls[:4]], queue)
        self.assertEqual([call.args[1:4] for call in calls[4:]], queue)
        self.assertEqual([call.args[-1]['temperature_c'] for call in calls], [25] * 4 + [50] * 4)


class SiteMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, {
            'tkinter': Mock(), 'tooltip_helper': SimpleNamespace(attach_tooltip=Mock()),
        }):
            cls.module = importlib.import_module('ui_site_selection')

    def test_bounds_use_all_absolute_device_positions_and_selected_subsite_only(self):
        devices = [Device('A', 1, 2, absolute_x=1001, absolute_y=2002),
                   Device('B', 10, 20, absolute_x=1010, absolute_y=2020),
                   Device('unknown', None, None)]
        site = Site('S', [Subsite('sub', devices), Subsite('other', [Device('A', -100, -200)])])
        items = self.module.site_map_items([site, Site('empty')], 'sub', ['A'])
        self.assertEqual(items[0].bounds, (-100, -200, 1010, 2020))
        self.assertEqual(items[0].selected_bounds, (1001, 2002, 1001, 2002))
        self.assertIsNone(items[1].bounds)
        self.assertIsNone(items[1].x)

    def test_boxes_fit_canvas_and_clicking_inside_toggles_site(self):
        dialog = self.module.SiteSelectionDialog.__new__(self.module.SiteSelectionDialog)
        sites = [Site('S', [Subsite('sub', [Device('A', 0, 0), Device('B', 1000, 2000)])])]
        dialog.devices = self.module.site_map_items(sites, 'sub', ['A'])
        dialog.selected_devices = set()
        dialog.prober_position = None
        dialog.canvas_width, dialog.canvas_height, dialog.margin = 700, 500, 60
        dialog.point_radius = 8
        dialog.device_items = {}
        dialog.canvas = Mock()
        dialog._draw_devices()
        transform = dialog._calculate_transform()
        for x, y in ((0, 0), (1000, 2000)):
            cx, cy = transform(x, y)
            self.assertTrue(60 <= cx <= 640)
            self.assertTrue(60 <= cy <= 440)
        rectangles = dialog.canvas.create_rectangle.call_args_list
        self.assertEqual(len(rectangles), 2)
        self.assertEqual(rectangles[1].kwargs['dash'], (4, 3))
        # Click away from the center, still inside the site's outer box.
        x, y = transform(100, 100)
        dialog._handle_click(x, y, False)
        self.assertEqual(dialog.selected_devices, {'S'})
        dialog._handle_click(x, y, True)
        self.assertEqual(dialog.selected_devices, set())


if __name__ == '__main__':
    unittest.main()
