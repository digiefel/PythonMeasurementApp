"""Exercise browser actions with real folder contents and stubbed Tk presentation."""

import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import data_management as data
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
        browser._sash_job = None
        browser._warned = set()
        browser.selected_identities = set()
        browser.map = browser.device_list = None
        browser.notes = TextValue()
        browser.status = TextValue()
        browser.search = TextValue()
        browser.annotations = {}
        browser.all_identities = [self.a, self.b]
        browser.measurements, browser.gallery_items = [], []
        browser.gallery_selection, browser.cards, browser.photos = set(), {}, []
        browser.page, browser.gallery_anchor = 0, None
        for name in ('window', 'notes_frame', 'save_label', 'status_box', 'clear_status_button', 'chip_list',
                     'view_frame', 'view_toggle', 'explanation', 'gallery_frame', 'gallery_canvas',
                     'page_label', 'gallery_label'):
            setattr(browser, name, Mock())

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

    def test_refresh_uses_list_fallback_for_unknown_or_unpositioned_devices(self):
        browser = self.browser
        missing = data.Identity('C', 'Unknown', 'Sub', 'D')
        self.make_measurement(missing)
        with patch.object(browser, '_show_view') as view, patch.object(browser, '_render_gallery'), patch.object(browser, '_warn_mismatches'):
            browser.refresh()
        view.assert_called_once_with(as_list=True)
        self.assertIn(missing, browser.all_identities)
        self.assertIn(missing, browser.missing)

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

    def test_gallery_modifier_selection_and_plain_click_open_plot(self):
        browser = self.browser
        plot = Path('/tmp/plot.png')
        browser.gallery_items = [SimpleNamespace(plot_files=(plot,)) for _ in range(5)]
        with patch.object(browser, '_open_artifacts') as opened:
            browser._gallery_click(1, SimpleNamespace(state=0))
            self.assertEqual(browser.gallery_selection, {1})
            opened.assert_called_once_with((plot,))
            browser._gallery_click(3, SimpleNamespace(state=1))
            self.assertEqual(browser.gallery_selection, {1, 2, 3})
            browser._gallery_click(2, SimpleNamespace(state=4))
            self.assertEqual(browser.gallery_selection, {1, 3})
            browser._gallery_click(4, SimpleNamespace(state=0), additive=True)
            self.assertEqual(browser.gallery_selection, {1, 3, 4})
            opened.assert_called_once()

    def test_warning_popup_consolidates_and_does_not_repeat_on_every_selection(self):
        self.make_measurement(self.a, wrong_header=True)
        self.browser.gallery_items = self.browser.measurements
        with patch.object(self.module, 'WarningPopup') as popup:
            self.browser._warn_mismatches()
            self.browser._warn_mismatches()
        popup.assert_called_once()
        self.assertIn('Wrong', popup.call_args.args[1][0])

    def test_correction_is_gated_while_running_and_passes_exact_scope_when_idle(self):
        browser = self.browser
        browser.is_running.return_value = True
        with patch.object(self.module, 'CorrectionDialog') as dialog, patch.object(self.module.messagebox, 'showinfo'):
            browser._correct(folders=[self.a.parts])
            dialog.assert_not_called()
            browser.is_running.return_value = False
            browser._correct(folders=[self.a.parts])
        dialog.assert_called_once_with(browser, (), [self.a.parts])

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
        dialog.browser, dialog.measurements, dialog.folders = browser, browser.measurements, ()
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
        fake_tk.TclError = type('TclError', (Exception,), {})
        fake_ttk = Mock()
        fake_ttk.Frame.side_effect = lambda *args, **kwargs: Mock(winfo_children=Mock(return_value=[]))
        sample_globals = self.module.SampleMap._create_dialog.__globals__
        with patch.object(self.module, 'tk', fake_tk), patch.object(self.module, 'ttk', fake_ttk), \
                patch.dict(sample_globals, {'tk': fake_tk, 'ttk': fake_ttk}):
            browser = self.module.DataManagementWindow(Mock(), self.browser.data_root, self.browser.sites, chip='C')
            self.assertIsNotNone(browser.map)
            self.assertIsNone(browser.device_list)
            self.assertEqual(len(browser.map.devices), 2)
            self.assertEqual(browser.map.devices[1].identity, self.b)
            browser.sites[0].subsites[0].devices[0].absolute_x = None
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
