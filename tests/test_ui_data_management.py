"""Exercise browser actions with real folder contents and stubbed Tk presentation."""

import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageTk

import data_management as data
from measurement_query import Condition, MeasurementQuery
from models import Device, Site, Subsite
from tests.test_ui_connections import load_ui


class TextValue:
    def __init__(self, value=''):
        self.value = value

    def get(self, *args):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **kwargs):
        pass

    def delete(self, *args):
        self.value = ''

    def insert(self, index, text):
        self.value = text

    def edit_modified(self, *args):
        return False

    def edit_reset(self):
        pass

    def trace_add(self, *args):
        return 'trace'


class DataBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, {'tkinter': Mock(), 'tooltip_helper': SimpleNamespace(attach_tooltip=Mock())}):
            cls.module = importlib.import_module('ui_data_management')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        browser = self.module.DataManagementWindow.__new__(self.module.DataManagementWindow)
        self.browser = browser
        browser.data_root = Path(self.temporary.name)
        browser.chip = 'C'
        browser.is_running = Mock(return_value=False)
        browser.sites = [Site('S', [Subsite('Sub', [Device('A', 0, 0), Device('B', 100, 200)])])]
        self.a = data.Identity('C', 'S', 'Sub', 'A')
        self.b = data.Identity('C', 'S', 'Sub', 'B')
        browser._notes_identity, browser._notes_job = None, None
        browser._notes_dirty = browser._loading_notes = False
        browser._sash_set = False
        browser._warned = set()
        browser.selected_identities = set()
        browser.map = browser.device_list = None
        browser.notes = TextValue()
        browser.status = TextValue()
        browser.search = TextValue()
        browser._gallery_width = 360
        browser._gallery_columns = 1
        browser._gallery_resize_job = browser._find_job = None
        browser._thumbnail_size = None
        browser._gallery_sources, browser._pictures = {}, {}
        browser.query = MeasurementQuery()
        browser.device_search = TextValue()
        browser._gallery_font = ('TkDefaultFont', 8)
        browser._gallery_line_height = 16
        browser.annotations = {}
        browser.layout = data.layout_devices(browser.sites, browser.chip)
        browser.notes_member = TextValue()
        browser.all_identities = [self.a, self.b]
        browser.measurements, browser.gallery_items = [], []
        browser.gallery_selection, browser.cards, browser.photos = set(), {}, []
        browser.page, browser.gallery_anchor = 0, None
        for name in ('window', 'notes_frame', 'notes_identity_label', 'gallery_header', 'notes_member_box', 'save_label', 'status_box', 'clear_status_button', 'chip_list', 'chip_button', 'chip_picker',
                     'view_frame', 'view_toggle', 'gallery_frame', 'gallery_canvas',
                     'page_label', 'gallery_label', 'filter_button', 'find_count'):
            setattr(browser, name, Mock())
        browser.gallery_frame.winfo_children.return_value = []
        browser.gallery_window = 1

    def make_measurement(self, identity, timestamp='20261006_120000', wrong_header=False):
        directory = identity.directory(self.browser.data_root)
        directory.mkdir(parents=True, exist_ok=True)
        base = '_'.join(identity.parts) + f'_{timestamp}_IV'
        header_identity = data.Identity('Wrong', 'S', 'Sub', identity.device) if wrong_header else identity
        header = '\n'.join(f'# {key}: {value}' for key, value in zip(data.IDENTITY_KEYS, header_identity.parts))
        (directory / f'{base}.csv').write_text(header + '\nV,I\n1,2\n', encoding='utf-8')
        (directory / f'{base}_plot.png').write_bytes(b'PNG')
        self.browser.measurements = data.scan_chip(self.browser.data_root, identity.chip)[1]

    def test_switching_devices_saves_previous_notes_and_loads_new_status(self):
        browser = self.browser
        data.write_notes(browser.data_root, self.b, 'OK', 'usable')
        browser._load_notes(self.a)
        browser.selected_identities = {self.a}
        browser.notes.value = 'new notes'
        browser.status.value = 'Bad'
        browser._schedule_save()
        with patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser._selection_changed({browser._key(self.b)})
        self.assertEqual(data.read_notes(browser.data_root, self.a), ('Bad', 'new notes'))
        self.assertEqual(browser.notes.value, 'usable')
        self.assertEqual(browser.status.value, 'OK')
        self.assertEqual(browser._notes_identity, self.b)
        self.assertEqual(browser.selected_identities, {self.b})
        browser.window.after_cancel.assert_called_once()

    def test_chip_picker_saves_notes_and_clears_device_scope_before_switching(self):
        browser = self.browser
        self.make_measurement(self.a)
        browser._load_notes(self.a)
        browser.notes.value = 'Keep this note when changing chip.'
        browser._notes_dirty = True
        browser.selected_identities = {self.a}
        browser.visible_chips = ['C', 'Other chip']
        browser.chip_list.curselection.return_value = (1,)
        with patch.object(browser, 'refresh') as refresh:
            browser._choose_chip()
        self.assertEqual(data.read_notes(browser.data_root, self.a)[1], browser.notes.value)
        self.assertEqual(browser.chip, 'Other chip')
        self.assertEqual(browser.selected_identities, set())
        refresh.assert_called_once()

    def test_status_autosaves_and_clears_without_modifying_notes(self):
        browser = self.browser
        browser._load_notes(self.a)
        browser.notes.value = 'test note'
        browser.status.value = 'Good'
        browser.map = Mock()
        browser._status_changed()
        self.assertEqual(data.read_notes(browser.data_root, self.a), ('Good', 'test note'))
        self.assertEqual(browser.annotations[browser._key(self.a)]['status'], 'Good')
        browser.map._draw_devices.assert_called_once()
        browser._clear_status()
        self.assertEqual(data.read_notes(browser.data_root, self.a), ('', 'test note'))

    def test_no_selection_shows_chip_gallery_and_multiple_devices_have_no_note_editor(self):
        browser = self.browser
        self.make_measurement(self.a)
        self.make_measurement(self.b)
        with patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser._selection_changed(set())
            self.assertEqual(len(browser.gallery_items), 2)
            browser._selection_changed({browser._key(self.a)})
            self.assertEqual(len(browser.gallery_items), 1)
            self.assertEqual(browser.gallery_items[0].identity, self.a)
            browser._selection_changed({browser._key(self.a), browser._key(self.b)})
        self.assertIsNone(browser._notes_identity)
        browser.status_box.configure.assert_called_with(state='disabled')

    def test_shared_location_combines_histories_and_keeps_individual_notes_editable(self):
        browser = self.browser
        second = data.Identity('C', 'S', 'Other', 'Alias')
        browser.sites[0].subsites.append(Subsite('Other', [Device('Alias', 0, 0)]))
        self.make_measurement(self.a)
        self.make_measurement(second, '20261008_120000')
        data.write_notes(browser.data_root, self.a, 'Bad', 'first notes')
        data.write_notes(browser.data_root, second, 'Good', 'alias notes')
        with patch.object(browser, '_show_view'), patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser.refresh()
            browser._selection_changed({browser._key(self.a), browser._key(second)})
            self.assertEqual({item.identity for item in browser.gallery_items}, {self.a, second})
            self.assertEqual(len(browser.gallery_items), 2)
            browser.notes_member.set(browser._key(second))
            browser._choose_notes_member()
            self.assertEqual(browser.notes.value, 'alias notes')
            browser.notes.value = 'edited alias'
            browser._notes_dirty = True
            browser.save_notes()
        self.assertEqual(data.read_notes(browser.data_root, self.a), ('Bad', 'first notes'))
        self.assertEqual(data.read_notes(browser.data_root, second), ('Good', 'edited alias'))
        annotation = browser.annotations[browser._key(second)]
        self.assertEqual(annotation['measurement_count'], 1)
        self.assertEqual(annotation['last_measurement'], '2026-10-08')

    def test_refresh_preserves_single_selection_and_includes_new_measurements(self):
        browser = self.browser
        self.make_measurement(self.a)
        browser.selected_identities = {self.a}
        browser._notes_identity = self.a
        self.make_measurement(self.a, timestamp='20261006_130000')
        with patch.object(browser, '_show_view') as view, patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser.refresh()
        view.assert_called_once_with(as_list=False)
        self.assertEqual(len(browser.gallery_items), 2)
        self.assertEqual(browser._notes_identity, self.a)

    def test_unknown_device_does_not_replace_a_drawable_map(self):
        browser = self.browser
        missing = data.Identity('C', 'Unknown', 'Sub', 'D')
        self.make_measurement(missing)
        with patch.object(browser, '_show_view') as view, patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser.refresh()
        view.assert_called_once_with(as_list=False)
        self.assertIn(missing, browser.all_identities)
        self.assertIn(missing, browser.missing)

    def test_unpositioned_layout_device_does_not_replace_a_drawable_map(self):
        browser = self.browser
        browser.sites[0].subsites[0].devices[0].absolute_x = None
        with patch.object(browser, '_show_view') as view, patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser.refresh()
        view.assert_called_once_with(as_list=False)
        self.assertEqual(browser.missing, [self.a])

    def test_failed_autosave_prevents_switch_and_preserves_unsaved_text(self):
        browser = self.browser
        browser._load_notes(self.a)
        browser.selected_identities = {self.a}
        browser.notes.value = 'unsaved'
        browser._notes_dirty = True
        browser.map = Mock()
        with patch.object(self.module, 'write_notes', side_effect=OSError('read only')), patch.object(self.module.messagebox, 'showerror'):
            browser._selection_changed({browser._key(self.b)})
            self.assertFalse(browser.close())
        self.assertEqual(browser.selected_identities, {self.a})
        self.assertEqual(browser.map.selected_devices, {browser._key(self.a)})
        self.assertEqual(browser.notes.value, 'unsaved')
        self.assertTrue(browser._notes_dirty)
        browser.window.destroy.assert_not_called()

    def test_gallery_click_selects_modifiers_extend_selection_and_double_click_opens(self):
        browser = self.browser
        plot = Path('/tmp/plot.png')
        browser.gallery_items = [SimpleNamespace(plot_files=(plot,)) for _ in range(5)]
        with patch.object(browser, '_open_artifacts') as opened:
            browser._gallery_click(1, SimpleNamespace(state=0))
            self.assertEqual(browser.gallery_selection, {1})
            opened.assert_not_called()
            browser._gallery_click(3, SimpleNamespace(state=1))
            self.assertEqual(browser.gallery_selection, {1, 2, 3})
            browser._gallery_click(2, SimpleNamespace(state=4))
            self.assertEqual(browser.gallery_selection, {1, 3})
            browser._gallery_click(4, SimpleNamespace(state=0), additive=True)
            self.assertEqual(browser.gallery_selection, {1, 3, 4})
            opened.assert_not_called()
            browser._gallery_open(2)
            self.assertEqual(browser.gallery_selection, {2})
            opened.assert_called_once_with((plot,))

    def test_warning_popup_consolidates_and_does_not_repeat_on_every_selection(self):
        self.make_measurement(self.a, wrong_header=True)
        self.browser.gallery_items = self.browser.measurements
        with patch.object(self.module, 'WarningPopup') as popup:
            self.browser._warn_mismatches()
            self.browser._warn_mismatches()
        popup.assert_called_once()
        self.assertIn('Wrong', popup.call_args.args[1][0])

    def test_select_all_includes_other_pages_and_correction_uses_only_selected_measurements(self):
        browser = self.browser
        browser.gallery_items = [object() for _ in range(browser.PAGE_SIZE + 4)]
        browser.page = 1
        browser._select_all_measurements()
        self.assertEqual(browser.gallery_selection, set(range(len(browser.gallery_items))))
        with patch.object(self.module, 'CorrectionDialog') as dialog:
            browser._correct_measurements()
        dialog.assert_called_once_with(browser, browser.gallery_items)

    def test_query_filters_gallery_within_device_scope_and_clear_restores_it(self):
        self.make_measurement(self.a, '20261006_120000')
        self.make_measurement(self.a, '20261008_120000')
        self.make_measurement(self.b, '20261008_130000')
        browser = self.browser
        browser.selected_identities = {self.a}
        with patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            self.assertTrue(browser._apply_query(MeasurementQuery(conditions=(Condition('Date', 'on or after', '2026-10-08'),))))
            self.assertEqual([(item.identity, item.timestamp) for item in browser.gallery_items], [(self.a, '20261008_120000')])
            browser._apply_query(MeasurementQuery())
            self.assertEqual(len(browser.gallery_items), 2)
        self.assertEqual(browser.selected_identities, {self.a})

    def test_filter_dialog_builds_and_applies_date_range_with_conditions(self):
        self.make_measurement(self.a)
        module = importlib.import_module('ui_measurement_filter')
        fake_tk = Mock()
        fake_tk.StringVar.side_effect = lambda *args, **kwargs: TextValue(kwargs.get('value', ''))
        apply = Mock(return_value=True)
        query = MeasurementQuery(conditions=(Condition('Procedure', 'contains', 'IV'),),
                                 from_date='2026-10-01', to_date='2026-10-08')
        with patch.object(module, 'tk', fake_tk), patch.object(module, 'ttk', Mock()):
            dialog = module.MeasurementFilterDialog(Mock(), query, self.browser.measurements, apply)
            dialog._submit()
        apply.assert_called_once_with(query)
        dialog.window.destroy.assert_called_once()

    def test_name_search_centers_matches_without_changing_device_or_gallery_selection(self):
        browser = self.browser
        browser.map = Mock()
        browser.selected_identities = {self.b}
        browser.gallery_selection = {2}
        browser.device_search.set('A')
        browser._find_devices()
        browser.map.focus_matches.assert_called_once_with({browser._key(self.a)})
        self.assertEqual(browser.selected_identities, {self.b})
        self.assertEqual(browser.gallery_selection, {2})

    def test_grid_resize_preserves_selection_and_reuses_loaded_larger_plot_previews(self):
        for second in range(6):
            self.make_measurement(self.a, f'20261008_12000{second}')
        browser = self.browser
        browser.gallery_items = browser.measurements
        for item in browser.gallery_items:
            self.module.Image.new('RGB', (600, 240), 'white').save(item.plot_files[0])
        self.module.Image.new('RGB', (960, 960), 'white').save(browser.gallery_items[0].plot_files[0])
        browser.gallery_items[1].plot_files[0].write_bytes(b'Not a readable image')
        self.module.Image.new('RGB', (600, 900), 'white').save(browser.gallery_items[-1].plot_files[0])
        browser._gallery_width = 620
        browser.gallery_selection = {2}
        fake_tk = Mock()
        with patch.object(self.module, 'tk', fake_tk), \
                patch.object(self.module.ImageTk, 'PhotoImage') as photos, \
                patch.object(self.module.Image, 'open', wraps=self.module.Image.open) as opened:
            browser._render_gallery()
            self.assertEqual(browser._gallery_columns, 3)
            side = 620 // 3 - 2
            for card in browser.cards.values():
                card.configure.assert_any_call(width=side, height=side + 32)
            self.assertNotIn(1, browser._gallery_sources)
            self.assertEqual(photos.call_args_list[0].args[0].size, (side - 6, side - 6))
            self.assertEqual(photos.call_args.args[0].height, side - 6)
            self.assertAlmostEqual(photos.call_args.args[0].width / photos.call_args.args[0].height, 2 / 3, delta=0.01)
            browser._resize_gallery(SimpleNamespace(width=930))
            browser._resize_thumbnails()
            self.assertEqual(browser._gallery_columns, 5)
            side = 930 // 5 - 2
            for card in browser.cards.values():
                card.configure.assert_any_call(width=side, height=side + 32)
            self.assertEqual(photos.call_args_list[-5].args[0].size, (side - 6, side - 6))
            self.assertEqual(photos.call_args.args[0].height, side - 6)
            self.assertEqual(opened.call_count, len(browser.gallery_items))
        self.assertEqual(browser.gallery_selection, {2})

    def test_correction_dialog_builds_and_moves_selected_artifacts_without_device_notes(self):
        self.make_measurement(self.a)
        self.make_measurement(self.b)
        data.write_notes(self.browser.data_root, self.a, 'Bad', 'physical device note')
        selected = [item for item in self.browser.measurements if item.identity == self.a]
        fake_tk = Mock()
        fake_tk.StringVar.side_effect = lambda *args, **kwargs: TextValue(kwargs.get('value', ''))
        with patch.object(self.module, 'tk', fake_tk), patch.object(self.module, 'ttk', Mock()):
            dialog = self.module.CorrectionDialog(self.browser, selected)
        dialog.variables['Chip'].set('Corrected')
        dialog._preview()
        self.assertEqual({item.source for item in dialog.plan}, set(selected[0].data_files + selected[0].plot_files))
        self.browser.refresh = Mock()
        dialog._apply()
        self.assertEqual(data.read_notes(self.browser.data_root, self.a), ('Bad', 'physical device note'))
        self.assertEqual({item.identity for item in data.scan_chip(self.browser.data_root, 'C')[1]}, {self.b})
        self.assertEqual({item.identity for item in data.scan_chip(self.browser.data_root, 'Corrected')[1]},
                         {data.Identity('Corrected', 'S', 'Sub', 'A')})

    def test_correction_is_gated_while_running_and_passes_exact_scope_when_idle(self):
        browser = self.browser
        browser.is_running.return_value = True
        with patch.object(self.module, 'CorrectionDialog') as dialog, patch.object(self.module.messagebox, 'showinfo'):
            browser._correct(measurements=['selected measurement'])
            dialog.assert_not_called()
            browser.is_running.return_value = False
            browser._correct(measurements=['selected measurement'])
        dialog.assert_called_once_with(browser, ['selected measurement'])

    def test_close_flushes_notes_before_destroying_window(self):
        browser = self.browser
        browser._load_notes(self.a)
        browser.notes.value = 'last edit'
        browser._notes_dirty = True
        self.assertTrue(browser.close())
        self.assertEqual(data.read_notes(browser.data_root, self.a), ('', 'last edit'))
        browser.window.destroy.assert_called_once()

    def test_preview_and_apply_use_real_files_and_switch_to_corrected_chip(self):
        self.make_measurement(self.a)
        browser = self.browser
        dialog = self.module.CorrectionDialog.__new__(self.module.CorrectionDialog)
        dialog.browser, dialog.measurements = browser, browser.measurements
        dialog.window, dialog.apply_button = Mock(), Mock()
        dialog.preview = TextValue()
        dialog.variables = {key: TextValue('NewChip' if key == 'Chip' else '') for key in data.IDENTITY_KEYS}
        dialog.plan = ()
        dialog._preview()
        self.assertEqual(len(dialog.plan), 2)
        self.assertIn('CSV header → NewChip / S / Sub / A', dialog.preview.value)
        browser.refresh = Mock()
        dialog._apply()
        self.assertEqual(browser.chip, 'NewChip')
        self.assertEqual(browser.selected_identities, {data.Identity('NewChip', 'S', 'Sub', 'A')})
        browser.refresh.assert_called_once()
        self.assertFalse(data.scan_chip(browser.data_root, 'NewChip')[1][0].warnings)

    def test_changed_fields_invalidate_preview_and_run_start_prevents_apply(self):
        dialog = self.module.CorrectionDialog.__new__(self.module.CorrectionDialog)
        dialog.browser, dialog.window, dialog.apply_button, dialog.preview = self.browser, Mock(), Mock(), TextValue('preview')
        dialog.plan = ('pending',)
        dialog._invalidate()
        self.assertEqual(dialog.plan, ())
        self.assertEqual(dialog.preview.value, '')
        self.browser.is_running.return_value = True
        with patch.object(self.module, 'apply_correction') as apply, patch.object(self.module.messagebox, 'showinfo'):
            dialog._apply()
        apply.assert_not_called()

    def test_main_ui_opens_browser_for_selected_output_directory(self):
        module = load_ui()
        ui = module.MainUI.__new__(module.MainUI)
        ui._data_manager = None
        ui.root = Mock()
        ui.config = SimpleNamespace(data={'output_dir': str(self.browser.data_root)}, sites=self.browser.sites)
        ui.chip_var = TextValue('C')
        ui.update_output_dir_from_ui = Mock(return_value=True)
        ui._running = False
        with patch.dict(sys.modules, {'ui_data_management': self.module}):
            with patch.object(self.module, 'DataManagementWindow') as factory:
                ui.open_data_management()
        self.assertEqual(factory.call_args.args, (ui.root, str(self.browser.data_root), self.browser.sites))
        self.assertEqual(factory.call_args.kwargs['chip'], 'C')
        self.assertFalse(factory.call_args.kwargs['is_running']())

    def test_window_builders_create_map_and_fallback_list_with_production_widgets_logic(self):
        fake_tk = Mock()
        fake_tk.StringVar.side_effect = lambda *args, **kwargs: TextValue(kwargs.get('value', ''))
        fake_tk.Text.return_value.edit_modified.return_value = False
        fake_tk.Canvas.return_value.bbox.return_value = (0, 0, 20, 12)
        fake_tk.TclError = type('TclError', (Exception,), {})
        fake_ttk = Mock()
        fake_ttk.Frame.side_effect = lambda *args, **kwargs: Mock(winfo_children=Mock(return_value=[]))
        sample_globals = self.module.SampleMap._create_dialog.__globals__
        with patch.object(self.module, 'tk', fake_tk), patch.object(self.module, 'ttk', fake_ttk), \
                patch.object(self.module.tkfont, 'Font', return_value=Mock(metrics=Mock(return_value=16))), \
                patch.dict(sample_globals, {'tk': fake_tk, 'ttk': fake_ttk}):
            browser = self.module.DataManagementWindow(Mock(), self.browser.data_root, self.browser.sites, chip='C')
            self.assertIsNotNone(browser.map)
            self.assertIsNone(browser.device_list)
            self.assertEqual(len(browser.map.devices), 2)
            self.assertEqual(browser.map.devices[1].identity, self.b)
            browser.sites[0].subsites[0].devices[0].absolute_x = None
            browser.refresh()
            self.assertIsNotNone(browser.map)
            self.assertIsNone(browser.device_list)
            self.assertEqual([item.identity for item in browser.map.unpositioned_devices], [self.a])
            self.assertIsNotNone(browser.map.manual_list)
            self.assertEqual([item.identity for item in browser.map.devices], [self.b])
            browser.sites[0].subsites[0].devices[1].absolute_y = None
            browser.refresh()
            self.assertIsNone(browser.map)
            self.assertIsNotNone(browser.device_list)
            self.assertEqual(len(browser.all_identities), 2)

    def test_existing_browser_refreshes_layout_and_different_output_folder_closes_it(self):
        module = load_ui()
        ui = module.MainUI.__new__(module.MainUI)
        ui._data_manager = Mock(data_root=self.browser.data_root)
        ui.root = Mock()
        ui.config = SimpleNamespace(data={'output_dir': str(self.browser.data_root)}, sites=self.browser.sites)
        ui.chip_var = TextValue('C')
        ui.update_output_dir_from_ui = Mock(return_value=True)
        ui._running = False
        ui.open_data_management()
        ui._data_manager.refresh.assert_called_once()
        ui._data_manager.window.lift.assert_called_once()
        ui.config.data['output_dir'] = str(self.browser.data_root / 'different')
        old = ui._data_manager
        with patch.dict(sys.modules, {'ui_data_management': self.module}):
            with patch.object(self.module, 'DataManagementWindow') as factory:
                ui.open_data_management()
        old.close.assert_called_once()
        factory.assert_called_once()


if __name__ == '__main__':
    unittest.main()
