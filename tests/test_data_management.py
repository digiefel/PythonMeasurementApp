"""Folder-backed browsing and lossless batch correction without GUI or instruments."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import data_management as data
from models import Device, Site, Subsite


class DataManagementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = data.Identity('Chip_A', 'S_01', 'Sub_site', 'Dev_1')
        self.folder = self.identity.directory(self.root)
        self.folder.mkdir(parents=True)
        self.payload = b'V,I\r\n0.001,1.234567890123e-12\r\n-1.0,-2.0e-9\r\n'

    def measurement(self, tag='IV', timestamp='20261006_120000', identity=None, header_identity=None, combo=False):
        identity = identity or self.identity
        header_identity = header_identity or identity
        folder = identity.directory(self.root)
        folder.mkdir(parents=True, exist_ok=True)
        base = '_'.join(identity.parts) + f'_{timestamp}_300K_{tag}'
        csv = folder / f'{base}{"_c001" if combo else ""}.csv'
        header = b'# Procedure: IV sweep\r\n# Timestamp: ' + timestamp.encode() + b'\r\n'
        for key, value in zip(data.IDENTITY_KEYS, header_identity.parts):
            header += f'# {key}: {value}\r\n'.encode()
        header += b'# Parameters:\r\n#   Chip: leave this parameter alone\r\n#   bias: 1.2\r\n'
        csv.write_bytes(header + self.payload)
        png = folder / f'{base}_plot.png'
        png.write_bytes(b'PNG bytes')
        return csv, png

    def scan(self):
        return data.scan_chip(self.root, self.identity.chip)[1]

    def test_scan_groups_plots_and_combo_csvs_and_sorts_newest_first(self):
        csv, png = self.measurement(combo=True)
        second = csv.with_name(csv.name.replace('_c001', '_c002'))
        second.write_bytes(csv.read_bytes())
        self.measurement(timestamp='20261007_120000')
        items = self.scan()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].timestamp, '20261007_120000')
        self.assertEqual(set(items[1].data_files), {csv, second})
        self.assertEqual(items[1].plot_files, (png,))
        self.assertFalse(items[1].warnings)

    def test_scan_reports_directory_header_mismatch_and_missing_metadata(self):
        wrong = data.Identity('Wrong', 'Elsewhere', 'Other', 'D')
        self.measurement(header_identity=wrong)
        (self.folder / 'legacy.csv').write_bytes(self.payload)
        warnings = [warning for item in self.scan() for warning in item.warnings]
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any(wrong.label in warning and self.identity.label in warning for warning in warnings))
        self.assertTrue(any('metadata missing' in warning for warning in warnings))

    def test_empty_root_and_plot_without_data_are_browsable(self):
        self.assertEqual(data.chips_in(self.root), ['Chip_A'])
        self.assertEqual(data.scan_chip(self.root, 'new'), ([], []))
        (self.folder / 'only_plot.png').write_bytes(b'PNG')
        item = self.scan()[0]
        self.assertEqual(item.name, 'only')
        self.assertEqual(item.data_files, ())

    def test_notes_roundtrip_and_arbitrary_legacy_notes_remain_notes(self):
        notes = self.folder / 'notes.txt'
        notes.write_text('broken\nStatus: Bad\n', encoding='utf-8')
        self.assertEqual(data.read_notes(self.root, self.identity), ('', 'broken\nStatus: Bad\n'))
        for status in data.STATUSES:
            data.write_notes(self.root, self.identity, status, 'a note\nsecond line\n')
            self.assertEqual(data.read_notes(self.root, self.identity), (status, 'a note\nsecond line\n'))
        with self.assertRaises(ValueError):
            data.write_notes(self.root, self.identity, 'broken', '')

    def test_notes_can_be_saved_before_a_device_has_measurements(self):
        identity = data.Identity('New', 'S', 'Sub', 'D')
        data.write_notes(self.root, identity, '', '')
        self.assertFalse(identity.directory(self.root).exists())
        data.write_notes(self.root, identity, 'OK', '')
        self.assertEqual(data.read_notes(self.root, identity), ('OK', ''))
        self.assertEqual(data.scan_chip(self.root, 'New')[0], [identity])

    def test_partial_correction_keeps_notes_and_other_measurements(self):
        csv, png = self.measurement()
        untouched_csv, untouched_png = self.measurement(tag='PUND')
        data.write_notes(self.root, self.identity, 'Bad', 'damaged')
        selected = next(item for item in self.scan() if item.name.endswith('_IV'))
        plan = data.plan_correction(self.root, [selected], changes={'Chip': 'Correct_Chip', 'Site': 'S02'})
        self.assertEqual(len(plan), 2)
        data.apply_correction(self.root, plan)
        self.assertFalse(csv.exists())
        self.assertFalse(png.exists())
        self.assertTrue(untouched_csv.exists())
        self.assertTrue(untouched_png.exists())
        self.assertEqual(data.read_notes(self.root, self.identity), ('Bad', 'damaged'))
        new = data.Identity('Correct_Chip', 'S02', 'Sub_site', 'Dev_1')
        corrected = data.scan_chip(self.root, new.chip)[1][0]
        self.assertEqual(corrected.identity, new)
        self.assertFalse(corrected.warnings)
        self.assertTrue(corrected.data_files[0].read_bytes().endswith(self.payload))
        self.assertIn(b'#   Chip: leave this parameter alone\r\n', corrected.data_files[0].read_bytes())
        self.assertEqual(corrected.plot_files[0].read_bytes(), b'PNG bytes')
        self.assertIn('_20261006_120000_300K_IV.csv', corrected.data_files[0].name)

    def test_folder_correction_carries_notes_and_removes_empty_old_hierarchy(self):
        self.measurement()
        data.write_notes(self.root, self.identity, 'Good', 'ready')
        plan = data.plan_correction(self.root, folders=[self.identity.parts[:2]], changes={'Chip': 'New', 'Site': 'NewSite'})
        self.assertEqual(len(plan), 3)
        data.apply_correction(self.root, plan)
        new = data.Identity('New', 'NewSite', 'Sub_site', 'Dev_1')
        self.assertEqual(data.read_notes(self.root, new), ('Good', 'ready'))
        self.assertFalse((self.root / self.identity.chip).exists())
        self.assertFalse(data.scan_chip(self.root, 'New')[1][0].warnings)

    def test_header_repair_in_place_preserves_bom_numeric_bytes_and_parameters(self):
        csv, png = self.measurement(header_identity=data.Identity('Wrong', 'Wrong', 'Wrong', 'Wrong'))
        csv.write_bytes(b'\xef\xbb\xbf' + csv.read_bytes())
        plot_bytes = png.read_bytes()
        plan = data.plan_correction(self.root, self.scan())
        data.apply_correction(self.root, plan)
        self.assertEqual(data.metadata_identity(data.read_metadata(csv)), self.identity)
        self.assertTrue(csv.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertTrue(csv.read_bytes().endswith(self.payload))
        self.assertEqual(png.read_bytes(), plot_bytes)

    def test_missing_identity_headers_are_added_without_changing_data(self):
        source, destination = self.folder / 'old.csv', self.folder / 'new.csv'
        source.write_bytes(self.payload)
        data.rewrite_csv_identity(source, destination, self.identity)
        self.assertEqual(data.metadata_identity(data.read_metadata(destination)), self.identity)
        self.assertTrue(destination.read_bytes().endswith(self.payload))

    def test_filename_repair_recognizes_header_identity_and_preserves_combo_suffix(self):
        old = self.identity
        wrong = data.Identity('Old', 'S0', 'Sub0', 'Dev0')
        path = Path('_'.join(wrong.parts) + '_20261006_120000_WGFMU_Sampling_c003.csv')
        new = old.corrected({'Chip': 'New'})
        corrected = data.corrected_filename(path, old, new, wrong)
        self.assertEqual(corrected, '_'.join(new.parts) + '_20261006_120000_WGFMU_Sampling_c003.csv')

    def test_existing_or_duplicate_destinations_are_rejected_before_writes(self):
        self.measurement()
        selected = self.scan()
        plan = data.plan_correction(self.root, selected, changes={'Chip': 'New'})
        destination = plan[0].destination
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            data.plan_correction(self.root, selected, changes={'Chip': 'New'})
        with self.assertRaises(FileExistsError):
            data.apply_correction(self.root, plan)
        self.assertEqual(destination.read_bytes(), b'existing')
        other = data.Identity('Chip_A', 'Other', 'Sub_site', 'Dev_1')
        self.measurement(identity=other)
        with self.assertRaises(ValueError):
            data.plan_correction(self.root, self.scan(), changes={'Site': 'Same'})

    def test_changed_source_invalidates_preview(self):
        csv, _ = self.measurement()
        plan = data.plan_correction(self.root, self.scan(), changes={'Chip': 'New'})
        csv.write_bytes(csv.read_bytes() + b'2,3\r\n')
        with self.assertRaisesRegex(ValueError, 'changed since preview'):
            data.apply_correction(self.root, plan)
        self.assertFalse((self.root / 'New').exists())

    def test_failed_install_rolls_back_prior_outputs_and_in_place_headers(self):
        self.measurement(header_identity=data.Identity('Wrong', 'S', 'Sub', 'D'))
        originals = {path: path.read_bytes() for item in self.scan() for path in item.files}
        for changes in ({'Chip': 'New'}, {}):
            with self.subTest(changes=changes):
                plan = data.plan_correction(self.root, self.scan(), changes=changes)
                original_copy = data.shutil.copyfileobj
                original_replace = data.os.replace

                def copy(reader, writer, *args):
                    if Path(writer.name) == plan[-1].destination:
                        writer.write(b'partial')
                        raise OSError('disk full')
                    return original_copy(reader, writer, *args)

                def replace(source, destination):
                    if Path(destination) == plan[-1].destination:
                        raise OSError('disk full')
                    return original_replace(source, destination)

                with patch.object(data.shutil, 'copyfileobj', side_effect=copy), patch.object(data.os, 'replace', side_effect=replace):
                    with self.assertRaises(OSError):
                        data.apply_correction(self.root, plan)
                self.assertEqual({path: path.read_bytes() for path in originals}, originals)
                for item in plan:
                    if item.destination != item.source:
                        self.assertFalse(item.destination.exists())
                if changes:
                    self.assertFalse((self.root / 'New').exists())
                self.assertFalse(list(self.root.glob('.assignment-*')))

    def test_failed_source_removal_restores_already_removed_files(self):
        self.measurement()
        plan = data.plan_correction(self.root, self.scan(), changes={'Chip': 'New'})
        originals = {item.source: item.source.read_bytes() for item in plan}
        original_unlink = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == plan[-1].source:
                raise OSError('cannot remove source')
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', unlink):
            with self.assertRaises(OSError):
                data.apply_correction(self.root, plan)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        self.assertTrue(all(not item.destination.exists() for item in plan))

    def test_names_and_symlinks_cannot_escape_the_data_folder(self):
        self.measurement()
        for value in ('../escape', '/tmp/escape', 'a\\b', '..', 'bad\nname'):
            with self.assertRaises(ValueError):
                data.plan_correction(self.root, self.scan(), changes={'Chip': value})
        (self.root / 'Link').symlink_to(self.root / self.identity.chip, target_is_directory=True)
        with self.assertRaises(ValueError):
            data.plan_correction(self.root, self.scan(), changes={'Chip': 'Link'})

    def test_geometry_uses_absolute_positions_and_falls_back_for_missing_devices(self):
        device = Device('Dev_1', 1, 2, absolute_x=101, absolute_y=202, tags=['layout-tag'])
        sites = [Site('S_01', [Subsite('Sub_site', [device])])]
        layout = data.layout_devices(sites, self.identity.chip)
        self.assertIs(layout[self.identity], device)
        self.assertFalse(data.missing_geometry(layout, [self.identity]))
        unknown = data.Identity(self.identity.chip, 'Missing', 'Sub_site', 'D')
        self.assertEqual(data.missing_geometry(layout, [unknown]), [unknown])
        device.absolute_y = None
        self.assertEqual(data.missing_geometry(layout, [self.identity]), [self.identity])
        self.assertEqual(device.tags, {'layout-tag'})

    def test_selection_annotations_are_chip_site_specific_and_do_not_change_layout_tags(self):
        device = Device('Dev_1', 1, 2, tags=['layout-tag'])
        sites = [Site('S_01', [Subsite('Sub_site', [device])]), Site('S02', [Subsite('Sub_site', [device])])]
        data.write_notes(self.root, self.identity, 'Bad', 'leaky')
        result = data.selection_annotations(self.root, self.identity.chip, sites[:1], 'Sub_site', ['Dev_1'])
        self.assertEqual(result['Dev_1']['status'], 'Bad')
        self.assertIn('leaky', result['Dev_1']['details'])
        self.assertTrue(result['Dev_1']['has_notes'])
        result = data.selection_annotations(self.root, self.identity.chip, sites, 'Sub_site', ['Dev_1'])
        self.assertEqual(result['Dev_1']['status'], 'Mixed')
        self.assertIn('S02', result['Dev_1']['details'])
        self.assertEqual(data.selection_annotations(self.root, 'OtherChip', sites, 'Sub_site', ['Dev_1']), {})
        self.assertEqual(device.tags, {'layout-tag'})


if __name__ == '__main__':
    unittest.main()
