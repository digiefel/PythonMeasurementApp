"""Exercise viewport navigation and selection using the production canvas logic."""

import importlib
import itertools
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from models import Device, Site, Subsite


class DeviceCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, {
            'tkinter': Mock(), 'tooltip_helper': SimpleNamespace(attach_tooltip=Mock()),
        }):
            cls.module = importlib.import_module('ui_device_selection')
            cls.site_module = importlib.import_module('ui_site_selection')
            cls.sample_module = importlib.import_module('ui_sample_view')

    def setUp(self):
        self.dialog = self.module.DeviceSelectionDialog.__new__(self.module.DeviceSelectionDialog)
        self.dialog.devices = [Device('A', 0, 0), Device('B', 1000, 500), Device('C', 2000, 1000)]
        self.dialog.unpositioned_devices = []
        self.dialog.selected_devices = {'B'}
        self.dialog.canvas_width, self.dialog.canvas_height, self.dialog.margin = 700, 500, 60
        self.dialog.point_radius, self.dialog.label_offset = 8, 6
        self.dialog._view = self.dialog._pan_start = None
        self.dialog.drag_start = self.dialog.selection_rect = None
        self.dialog.device_items = {}
        self.dialog.prober_position = None
        self.dialog.manual_list = None
        self.dialog.annotations = {}
        self.dialog._annotation_window = None
        self.dialog.canvas = Mock()
        self.dialog.canvas.bbox.return_value = (0, 0, 20, 12)
        self.dialog.selection_label = Mock()

    def navigate(self):
        self.dialog._zoom_at(230, 180, 3)
        self.dialog._on_pan_start(SimpleNamespace(x=30, y=40))
        self.dialog._on_pan_drag(SimpleNamespace(x=110, y=100))
        self.dialog._on_pan_end(SimpleNamespace())

    def test_zoom_keeps_cursor_coordinate_fixed_and_marker_size_constant(self):
        dialog = self.dialog
        x, y = dialog._calculate_transform()(1000, 500)
        before = dialog._calculate_transform()(0, 0)
        dialog._zoom_at(x, y, 3)
        anchor_x, anchor_y = dialog._calculate_transform()(1000, 500)
        self.assertAlmostEqual(anchor_x, x)
        self.assertAlmostEqual(anchor_y, y)
        after = dialog._calculate_transform()(0, 0)
        self.assertAlmostEqual(after[0] - x, (before[0] - x) * 3)
        self.assertAlmostEqual(after[1] - y, (before[1] - y) * 3)
        for call in dialog.canvas.create_oval.call_args_list:
            left, top, right, bottom = call.args
            self.assertAlmostEqual(right - left, 16)
            self.assertAlmostEqual(bottom - top, 16)

    def test_pan_moves_map_without_changing_selection_or_scale(self):
        dialog = self.dialog
        before = dialog._calculate_transform()(1000, 500)
        scale = dialog._view[0]
        dialog._on_pan_start(SimpleNamespace(x=30, y=40))
        dialog._on_pan_drag(SimpleNamespace(x=110, y=100))
        dialog._on_pan_end(SimpleNamespace())
        self.assertEqual(dialog._calculate_transform()(1000, 500), (before[0] + 80, before[1] + 60))
        self.assertEqual(dialog._view[0], scale)
        self.assertEqual(dialog.selected_devices, {'B'})
        self.assertIsNone(dialog._pan_start)
        dialog.canvas.configure.assert_called_with(cursor='')
        dialog.canvas.move.assert_called_once_with('map_content', 80, 60)
        dialog.canvas.create_oval.assert_not_called()
        dialog.canvas.delete.assert_not_called()

    def test_arrow_keys_pan_viewport_preserving_zoom_and_selection(self):
        dialog = self.dialog
        dialog._view = (0.5, 350, 250)
        for key, state, dx, dy in (('Left', 0, 40, 0), ('Right', 0, -40, 0),
                                   ('Up', 0, 0, 40), ('Down', 0, 0, -40), ('Right', 1, -160, 0)):
            with self.subTest(key=key, shift=bool(state)):
                before = dialog._view
                dialog.drag_start, dialog.selection_rect = (0, 0), 42
                self.assertEqual(dialog._on_arrow_key(SimpleNamespace(keysym=key, state=state)), 'break')
                self.assertEqual(dialog._view, (before[0], before[1] + dx, before[2] + dy))
                self.assertEqual(dialog.selected_devices, {'B'})
                self.assertIsNone(dialog.drag_start)
                self.assertIsNone(dialog.selection_rect)
        dialog.canvas.create_oval.assert_not_called()

    def test_click_and_ctrl_click_hit_device_after_navigation(self):
        self.navigate()
        dialog = self.dialog
        x, y = dialog._calculate_transform()(1000, 500)
        dialog._on_mouse_down(SimpleNamespace(x=x, y=y))
        dialog._on_mouse_up(SimpleNamespace(x=x, y=y, state=4))
        self.assertEqual(dialog.selected_devices, set())
        dialog._handle_click(x, y, False)
        self.assertEqual(dialog.selected_devices, {'B'})

    def test_rectangle_selection_uses_transformed_positions(self):
        self.navigate()
        dialog = self.dialog
        x, y = dialog._calculate_transform()(1000, 500)
        dialog.selected_devices = {'A'}
        dialog._handle_rectangle_selection(x - 10, y - 10, x + 10, y + 10, True)
        self.assertEqual(dialog.selected_devices, {'A', 'B'})
        dialog._handle_rectangle_selection(x - 10, y - 10, x + 10, y + 10, False)
        self.assertEqual(dialog.selected_devices, {'B'})

    def test_refresh_preserves_view_and_transforms_prober_marker(self):
        self.navigate()
        dialog = self.dialog
        view = dialog._view
        dialog.canvas.reset_mock()
        dialog.update_prober_position((100000, -100000))
        self.assertEqual(dialog._view, view)
        call = dialog.canvas.create_text.call_args_list[-1]
        x, y = dialog._calculate_transform()(*dialog.prober_position)
        self.assertEqual(call.args, (x, y + dialog.point_radius - 1 + 6))
        self.assertEqual(call.kwargs['text'], 'Prober')

    def test_fit_restores_all_bounds_including_prober_without_changing_selection(self):
        self.navigate()
        dialog = self.dialog
        dialog.update_prober_position((100000, -100000))
        dialog._fit_view()
        for x, y in dialog._plot_points() + [dialog.prober_position]:
            cx, cy = dialog._calculate_transform()(x, y)
            self.assertTrue(60 - 1e-8 <= cx <= 640 + 1e-8)
            self.assertTrue(60 - 1e-8 <= cy <= 440 + 1e-8)
        self.assertEqual(dialog.selected_devices, {'B'})

    def test_resize_preserves_scale_and_coordinate_at_view_center(self):
        self.navigate()
        dialog = self.dialog
        scale, offset_x, offset_y = dialog._view
        center = ((offset_x - 350) / scale, (250 - offset_y) / scale)
        dialog._on_canvas_resize(SimpleNamespace(width=900, height=700))
        self.assertEqual(dialog._view[0], scale)
        self.assertEqual(dialog._calculate_transform()(*center), (450, 350))

    def test_navigation_cancels_pending_rectangle_without_selecting_devices(self):
        for navigation in (
            lambda: self.dialog._zoom_at(350, 250, 2),
            lambda: self.dialog._on_pan_start(SimpleNamespace(x=30, y=40)),
            lambda: self.dialog._on_canvas_resize(SimpleNamespace(width=900, height=700)),
            self.dialog._fit_view,
        ):
            self.dialog.drag_start = (0, 0)
            self.dialog.selection_rect = 42
            navigation()
            self.dialog._on_mouse_up(SimpleNamespace(x=700, y=500, state=0))
            self.assertEqual(self.dialog.selected_devices, {'B'})
            self.assertIsNone(self.dialog.selection_rect)

    def test_mouse_wheel_handles_macos_windows_and_linux_directions(self):
        for platform, num, delta in (
            ('darwin', '??', 1), ('win32', '??', 120), ('linux', 4, 0),
        ):
            with self.subTest(platform=platform):
                self.dialog._view = None
                scale = self.dialog._fitted_view()[0]
                with patch.object(self.module.sys, 'platform', platform):
                    self.dialog._on_mouse_wheel(SimpleNamespace(num=num, delta=delta, x=300, y=200))
                    self.assertAlmostEqual(self.dialog._view[0], scale * 1.1)
                    self.dialog._on_mouse_wheel(SimpleNamespace(num=5 if num == 4 else num,
                                                               delta=-delta, x=300, y=200))
                    self.assertAlmostEqual(self.dialog._view[0], scale)

    def test_empty_map_can_navigate_and_fit_prober_only(self):
        self.dialog.devices = []
        self.navigate()
        self.dialog.update_prober_position((20000, -10000))
        self.dialog._fit_view()
        self.assertEqual(self.dialog._calculate_transform()(20000, -10000), (350, 250))

    def test_site_boxes_and_hit_testing_follow_navigation(self):
        dialog = self.dialog
        dialog.__class__ = self.site_module.SiteSelectionDialog
        sites = [Site('S', [Subsite('sub', [Device('A', 0, 0), Device('B', 1000, 500)])])]
        dialog.devices = self.site_module.site_map_items(sites, 'sub', ['A'])
        dialog.selected_devices = {'S'}
        self.navigate()
        item = dialog.devices[0]
        transform = dialog._calculate_transform()
        x, y = transform(100, 100)
        dialog._handle_click(x, y, True)
        self.assertEqual(dialog.selected_devices, set())
        dialog.canvas.reset_mock()
        dialog._draw_devices()
        calls = dialog.canvas.create_rectangle.call_args_list
        self.assertEqual(calls[0].args, dialog._canvas_bounds(item.bounds, transform))
        self.assertEqual(calls[1].args, dialog._canvas_bounds(item.selected_bounds, transform, padding=16))

    def test_status_colors_survive_selection_and_notes_have_a_visible_marker(self):
        dialog = self.dialog
        dialog.annotations = {'B': {'status': 'Bad', 'details': 'leaky', 'has_notes': True}}
        dialog._draw_devices()
        marker = dialog.canvas.create_oval.call_args_list[1]
        label = dialog.canvas.create_text.call_args_list[3]
        self.assertEqual(marker.kwargs['fill'], 'firebrick')
        self.assertEqual(marker.kwargs['outline'], 'blue')
        self.assertEqual(label.kwargs['text'], 'B [Bad] *')
        dialog._update_device_appearance('B', False)
        self.assertEqual(dialog.canvas.itemconfig.call_args_list[-2].kwargs['fill'], 'firebrick')
        self.assertEqual(dialog.canvas.itemconfig.call_args_list[-2].kwargs['outline'], 'firebrick')
        for status, color in (('Good', 'forestgreen'), ('OK', 'gold')):
            dialog.annotations['B']['status'] = status
            dialog._draw_devices()
            self.assertEqual(dialog.canvas.create_oval.call_args_list[-2].kwargs['fill'], color)

    def make_sample_map(self, items):
        dialog = self.dialog
        dialog.__class__ = self.sample_module.SampleMap
        dialog.devices = items
        dialog.selected_devices = set()
        dialog.on_context = Mock()
        dialog.on_select = Mock()
        dialog._context_start = None
        dialog._locations, dialog._sites, dialog._subsites = self.sample_module.build_geometry(items)
        dialog._location_by_key = {location.key: location for location in dialog._locations}
        dialog._region_by_key = {region.key: region for region in dialog._sites + dialog._subsites}
        dialog._region_items, dialog._location_items, dialog._levels = {}, {}, {}
        dialog._visible_locations, dialog._visible_regions = {}, []
        dialog._active_location_keys, dialog._active_region_keys = set(), set()
        dialog._manual_state = None
        return dialog

    def test_sample_map_context_click_is_distinct_from_panning(self):
        dialog = self.make_sample_map([SimpleNamespace(name='S/Sub/A', display_name='Sub/A', x=0, y=0,
                                                       identity=SimpleNamespace(site='S', subsite='Sub', device='A'))])
        dialog._draw_devices()
        x, y = dialog._calculate_transform()(0, 0)
        dialog._on_pan_start(SimpleNamespace(x=x, y=y))
        dialog._on_pan_end(SimpleNamespace(x=x, y=y))
        self.assertEqual(dialog.on_context.call_args.args[0], 'devices')
        dialog.on_context.reset_mock()
        dialog._on_pan_start(SimpleNamespace(x=x, y=y))
        dialog._on_pan_drag(SimpleNamespace(x=x + 30, y=y + 20))
        dialog._on_pan_end(SimpleNamespace(x=x + 30, y=y + 20))
        dialog.on_context.assert_not_called()

    def test_dense_sample_hides_devices_when_zoomed_out_and_culls_offscreen_locations(self):
        items = [SimpleNamespace(name=f'S/Sub/{x}_{y}', display_name=f'Sub/{x}_{y}', x=x * 10, y=y * 10,
                                 identity=SimpleNamespace(site='S', subsite='Sub', device=f'{x}_{y}'))
                 for x in range(30) for y in range(30)]
        dialog = self.make_sample_map(items)
        dialog._view = (0.2, 350, 250)
        dialog._draw_devices()
        dialog.canvas.create_oval.assert_not_called()
        self.assertFalse(dialog._visible_locations)
        selected = {items[0].name}
        dialog.selected_devices = selected
        dialog._zoom_at(350, 250, 15)
        self.assertGreater(len(dialog._visible_locations), 0)
        self.assertLess(len(dialog._visible_locations), len(items))
        markers = {key: entry[0] for key, entry in dialog._location_items.items()}
        dialog.canvas.reset_mock()
        dialog._draw_devices()
        dialog.canvas.create_oval.assert_not_called()
        self.assertEqual(markers, {key: entry[0] for key, entry in dialog._location_items.items()})
        dialog._zoom_at(350, 250, 1 / 15)
        self.assertFalse(dialog._visible_locations)
        self.assertEqual(dialog.selected_devices, selected)

    def test_measurements_and_assessments_are_visible_at_each_hierarchy_level_before_names(self):
        items = [SimpleNamespace(name=f'S/Sub/{x}', x=x, y=0,
                                 identity=SimpleNamespace(site='S', subsite='Sub', device=str(x)))
                 for x in range(0, 601, 50)]
        dialog = self.make_sample_map(items)
        ids = itertools.count(1)
        for method in ('create_rectangle', 'create_text', 'create_oval', 'create_arc'):
            getattr(dialog.canvas, method).side_effect = lambda *args, **kwargs: next(ids)
        dialog.annotations = {items[0].name: {'measurement_count': 2, 'status': 'Bad'},
                              items[1].name: {'measurement_count': 3, 'status': 'Good'}}

        def appearance(canvas_id):
            result = {}
            for call in dialog.canvas.itemconfigure.call_args_list:
                if call.args[0] == canvas_id:
                    result.update(call.kwargs)
            return result

        dialog._view = (0.1, 350, 250)
        dialog._draw_devices()
        site = dialog._region_items['site:S']
        self.assertNotEqual(appearance(site[0])['fill'], '#eef1f5')
        self.assertEqual(appearance(site[1])['text'], '5')
        self.assertEqual(appearance(site[1])['state'], 'normal')
        self.assertEqual({appearance(site[i])['fill'] for i in (2, 4)}, {'forestgreen', 'firebrick'})
        self.assertFalse(dialog._visible_locations)

        dialog._view = (0.35, 350, 250)
        dialog._draw_devices()
        subsite = dialog._region_items['subsite:S:0']
        self.assertEqual(appearance(subsite[1])['state'], 'normal')
        self.assertEqual(appearance(subsite[1])['text'], '5')
        self.assertNotEqual(appearance(subsite[0])['fill'], '#eef1f5')
        self.assertFalse(dialog._visible_locations)

        dialog._view = (0.5, 350, 250)
        dialog.selected_devices = {items[0].name}
        dialog._draw_devices()
        marker, count, _ = dialog._location_items[dialog._locations[0].key]
        self.assertEqual(appearance(marker)['fill'], 'firebrick')
        self.assertEqual(appearance(marker)['outline'], 'dodgerblue')
        self.assertEqual(appearance(count)['state'], 'normal')
        self.assertEqual(appearance(count)['text'], '2')
        self.assertEqual(appearance(subsite[1])['state'], 'hidden')
        dialog._view = (2, 350, 250)
        dialog._draw_devices()
        visible_texts = [call.kwargs['text'] for call in dialog.canvas.itemconfigure.call_args_list
                         if call.kwargs.get('state') == 'normal' and 'text' in call.kwargs]
        self.assertTrue(all(text.isdigit() for text in visible_texts))

        dialog.annotations[items[1].name]['status'] = 'OK'
        dialog._view = (0.1, 350, 250)
        dialog._draw_devices()
        self.assertEqual({appearance(site[i])['fill'] for i in (2, 4)}, {'gold', 'firebrick'})

    def test_unmeasured_region_and_device_have_no_count_or_measured_fill(self):
        items = [SimpleNamespace(name=f'S/Sub/{x}', x=x, y=0,
                                 identity=SimpleNamespace(site='S', subsite='Sub', device=str(x)))
                 for x in range(0, 601, 50)]
        dialog = self.make_sample_map(items)
        dialog._view = (0.1, 350, 250)
        dialog._draw_devices()
        self.assertTrue(any(call.kwargs.get('fill') == '#eef1f5'
                            for call in dialog.canvas.itemconfigure.call_args_list))
        dialog._view = (0.5, 350, 250)
        dialog._draw_devices()
        self.assertTrue(all(entry[1] is None for entry in dialog._location_items.values()))

    def test_device_fill_is_measurement_presence_outline_is_assessment_and_counts_contrast(self):
        for count, status, fill, outline, number_color in (
            (0, '', 'white', 'black', None), (4, '', 'black', 'black', 'white'),
            (0, 'Bad', 'white', 'firebrick', None), (3, 'Bad', 'firebrick', 'firebrick', 'white'),
            (0, 'OK', 'white', 'gold', None), (2, 'OK', 'gold', 'gold', 'black'),
            (0, 'Good', 'white', 'forestgreen', None), (1, 'Good', 'forestgreen', 'forestgreen', 'white'),
        ):
            with self.subTest(count=count, status=status):
                self.setUp()
                item = SimpleNamespace(name='S/Sub/D', x=0, y=0,
                                       identity=SimpleNamespace(site='S', subsite='Sub', device='D'))
                dialog = self.make_sample_map([item])
                dialog.annotations = {item.name: {'measurement_count': count, 'status': status}}
                dialog._draw_location(dialog._locations[0], 350, 250, 10, [], [])
                marker = dialog.canvas.itemconfigure.call_args_list[0].kwargs
                self.assertEqual(marker['fill'], fill)
                self.assertEqual(marker['outline'], outline)
                _, count_id, _ = dialog._location_items[dialog._locations[0].key]
                if count:
                    numbers = [call.kwargs for call in dialog.canvas.itemconfigure.call_args_list if 'text' in call.kwargs]
                    self.assertEqual(numbers[-1]['text'], str(count))
                    self.assertEqual(numbers[-1]['fill'], number_color)
                else:
                    self.assertIsNone(count_id)

    def test_hover_shows_identity_measurements_date_status_and_notes_without_canvas_labels(self):
        item = SimpleNamespace(name='S/Sub/D', x=0, y=0,
                               identity=SimpleNamespace(site='S', subsite='Sub', device='D'))
        dialog = self.make_sample_map([item])
        dialog.annotations = {item.name: {'measurement_count': 3, 'last_measurement': '20261008_120000',
                                         'status': 'Bad', 'has_notes': True, 'notes': 'Leaky after fatigue.'}}
        dialog._draw_devices()
        dialog.canvas.find_withtag.return_value = (123,)
        dialog.canvas.gettags.return_value = ('map_content', 'location', dialog._locations[0].key, 'map_hover')
        with patch.object(dialog, '_show_annotation') as shown:
            dialog._on_device_hover(SimpleNamespace())
            shown.assert_not_called()
            delay, callback = dialog.canvas.after.call_args.args
            self.assertGreater(delay, 0)
            callback()
        text = shown.call_args.args[1]
        for detail in ('Site S', 'D', 'Sub', '3 measurements', '2026-10-08', 'Bad', 'Leaky after fatigue.'):
            self.assertIn(detail, text)
        dialog.canvas.gettags.return_value = ('map_content', 'region', 'site:S', 'map_hover')
        with patch.object(dialog, '_show_annotation') as shown:
            dialog._on_device_hover(SimpleNamespace())
            dialog.canvas.after.call_args.args[1]()
        self.assertIn('3 measurements', shown.call_args.args[1])
        self.assertIn('Bad: 1 device', shown.call_args.args[1])

    def test_shared_location_selection_combines_members_and_ctrl_toggles_the_group(self):
        items = [SimpleNamespace(name=f'S/{sub}/A', x=0, y=0,
                                 identity=SimpleNamespace(site='S', subsite=sub, device='A'))
                 for sub in ('FeCap', 'FeCapBD')]
        dialog = self.make_sample_map(items)
        dialog._view = (2, 350, 250)
        dialog.annotations = {items[0].name: {'status': 'Bad', 'measurement_count': 2},
                              items[1].name: {'status': 'Good', 'measurement_count': 3}}
        dialog._draw_devices()
        self.assertEqual(dialog.canvas.create_oval.call_count, 1)
        self.assertEqual(dialog.canvas.create_arc.call_count, 2)
        target = dialog._target_at(350, 250)
        self.assertEqual(target.names, {item.name for item in items})
        dialog._handle_click(350, 250, False)
        self.assertEqual(dialog.selected_devices, target.names)
        dialog._handle_click(350, 250, True)
        self.assertEqual(dialog.selected_devices, set())
        counts = [call.kwargs.get('text') for call in dialog.canvas.itemconfigure.call_args_list]
        self.assertIn('5', counts)

    def test_collapsed_site_click_selects_devices_and_double_click_reveals_them(self):
        items = [SimpleNamespace(name=f'S/Sub/{x}', x=x, y=0,
                                 identity=SimpleNamespace(site='S', subsite='Sub', device=str(x)))
                 for x in (0, 1000)]
        dialog = self.make_sample_map(items)
        dialog._view = (0.1, 350, 250)
        dialog._draw_devices()
        self.assertFalse(dialog._visible_locations)
        dialog._handle_click(300, 250, False)
        self.assertEqual(dialog.selected_devices, {item.name for item in items})
        dialog._on_double_click(SimpleNamespace(x=300, y=250))
        self.assertTrue(dialog._visible_locations)
        self.assertEqual(dialog.selected_devices, {item.name for item in items})

    def test_keyboard_pan_refreshes_visibility_and_merged_location_hit_testing(self):
        items = [SimpleNamespace(name=f'S/{sub}/A', x=0, y=0,
                                 identity=SimpleNamespace(site='S', subsite=sub, device='A'))
                 for sub in ('FeCap', 'FeCapBD')]
        dialog = self.make_sample_map(items)
        dialog._view = (2, -80, 250)
        dialog._draw_devices()
        self.assertFalse(dialog._visible_locations)
        dialog._on_arrow_key(SimpleNamespace(keysym='Left', state=1))
        self.assertEqual(dialog._view, (2, 80, 250))
        target = dialog._target_at(80, 250)
        self.assertEqual(target.names, {item.name for item in items})
        self.assertTrue(dialog._visible_locations)
        self.assertEqual(dialog.selected_devices, set())
        self.assertFalse(dialog.on_context.called)

    def test_sample_site_box_and_padding_scale_together_when_zooming_out(self):
        dialog = self.make_sample_map([
            SimpleNamespace(name=f'S/Sub/{x}', display_name=f'Sub/{x}', x=x, y=x,
                            identity=SimpleNamespace(site='S', subsite='Sub', device='A'))
            for x in (0, 1000)])
        dialog.canvas.create_rectangle.side_effect = range(1, 100)
        dialog._draw_devices()
        before = dialog.site_bounds['S']
        dialog._zoom_at(350, 250, 0.25)
        after = dialog.site_bounds['S']
        for i, (old, new) in enumerate(zip(before, after)):
            anchor = 350 if i % 2 == 0 else 250
            self.assertAlmostEqual(new - anchor, (old - anchor) * 0.25)
        box_id = dialog._region_items['site:S'][0]
        drawn = [call.args[1:] for call in dialog.canvas.coords.call_args_list if call.args[0] == box_id]
        self.assertEqual(drawn[-1], after)
        self.assertAlmostEqual(after[0], dialog._calculate_transform()(1000, 0)[0] - 64 * dialog._view[0])

    def test_site_selection_outer_and_selected_boxes_scale_together(self):
        bounds = (0, 0, 1000, 500)
        for padding in (64, 16):
            with self.subTest(padding=padding):
                first = self.site_module.SiteSelectionDialog._canvas_bounds(
                    bounds, lambda x, y: (350 - x * 0.2, 250 + y * 0.2), padding)
                second = self.site_module.SiteSelectionDialog._canvas_bounds(
                    bounds, lambda x, y: (350 - x * 0.05, 250 + y * 0.05), padding)
                for i, (old, new) in enumerate(zip(first, second)):
                    anchor = 350 if i % 2 == 0 else 250
                    self.assertAlmostEqual(new - anchor, (old - anchor) * 0.25)

    def test_sample_pan_moves_site_context_bounds_without_recreating_canvas_items(self):
        dialog = self.make_sample_map([SimpleNamespace(name='S/Sub/A', display_name='Sub/A', x=0, y=0,
                                                       identity=SimpleNamespace(site='S', subsite='Sub', device='A'))])
        dialog._draw_devices()
        before = dialog.site_bounds['S']
        dialog.canvas.reset_mock()
        dialog._on_pan_start(SimpleNamespace(x=10, y=10))
        dialog._on_pan_drag(SimpleNamespace(x=90, y=70))
        dialog._on_pan_end(SimpleNamespace(x=90, y=70))
        self.assertEqual(dialog.site_bounds['S'], tuple(value + (80 if i % 2 == 0 else 60)
                                                       for i, value in enumerate(before)))
        dialog.canvas.move.assert_called_once_with('map_content', 80, 60)
        dialog.canvas.create_oval.assert_not_called()
        dialog.canvas.create_text.assert_not_called()
        dialog.canvas.create_rectangle.assert_not_called()
        dialog.canvas.delete.assert_not_called()


if __name__ == '__main__':
    unittest.main()
