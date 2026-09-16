import tempfile
import unittest
from pathlib import Path

from config import Config
from models import DeviceCsvError, compile_devices_csv, has_position


class DevicesCsvTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.csv_path = Path(self.temp_dir.name) / "devices.csv"

    def write_csv(self, contents):
        self.csv_path.write_text(contents, encoding="utf-8")

    def test_error_line_includes_header_and_blank_lines(self):
        self.write_csv("Site,Subsite,Device,X,Y\n\nS,A,D,bad,0\n")
        result = compile_devices_csv(str(self.csv_path))
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(result.errors[0].startswith("Row 3:"))

    def test_source_lines_include_multiline_records_and_blank_lines(self):
        self.write_csv(
            'Site,Subsite,Device,X,Y,Tags\nS,A,D,0,0,"first\nsecond"\n'
            '\nS,A,D,1,0,\n'
        )
        result = compile_devices_csv(str(self.csv_path))
        self.assertEqual([definition.row for definition in result.definitions], [3, 5])
        self.assertTrue(result.errors[0].startswith("Rows 3 and 5:"))

    def test_reload_same_path_reads_edits_and_preserves_tree_on_error(self):
        self.write_csv("Site,Subsite,Device,X,Y\nS,A,Old,0,0\n")
        config = Config(str(Path(self.temp_dir.name) / "config.json"), str(self.csv_path))
        self.write_csv("Site,Subsite,Device,X,Y\nS,A,New,10,20\n")
        config.reload_devices(str(self.csv_path), persist=True)
        device = config.sites[0].subsites[0].devices[0]
        self.assertEqual((device.name, device.x, device.y), ("New", -10, -20))
        sites = config.sites
        self.write_csv("Site,Subsite,Device,X,Y\nS,A,Bad,invalid,0\n")
        with self.assertRaises(DeviceCsvError):
            config.reload_devices(str(self.csv_path), persist=True)
        self.assertIs(config.sites, sites)

    def test_omitted_columns_and_blank_pairs_produce_unknown_positions(self):
        for contents in (
            "Site,Subsite,Device\nS,A,D\nS,A,E\n",
            "Site,Subsite,Device,X,Y\nS,A,D,,\nS,A,E,,\n",
        ):
            with self.subTest(contents=contents):
                self.write_csv(contents)
                result = compile_devices_csv(str(self.csv_path), raise_on_error=True)
                devices = result.sites[0].subsites[0].devices
                self.assertEqual(len(devices), 2)
                self.assertTrue(all(d.x is None and d.y is None for d in devices))
                self.assertTrue(all(not has_position(d) for d in devices))
                self.assertEqual(result.shared_positions, [])

    def test_partial_coordinate_pair_is_an_error(self):
        for header, cells in (("X,Y", "10,"), ("X,Y", ",20"), ("X", "10")):
            with self.subTest(header=header, cells=cells):
                self.write_csv(f"Site,Subsite,Device,{header}\nS,A,D,{cells}\n")
                result = compile_devices_csv(str(self.csv_path))
                self.assertEqual(len(result.errors), 1)
                self.assertIn("Row 2: Provide both X and Y", result.errors[0])

    def test_unknown_parent_propagates_to_device_absolute_position(self):
        for parent in ("S,,,,\n", "S,A,,,\n"):
            with self.subTest(parent=parent):
                self.write_csv("Site,Subsite,Device,X,Y\n" + parent + "S,A,D,10,20\n")
                result = compile_devices_csv(str(self.csv_path), raise_on_error=True)
                device = result.sites[0].subsites[0].devices[0]
                self.assertEqual((device.x, device.y), (-10, -20))
                self.assertEqual((device.absolute_x, device.absolute_y), (None, None))

    def test_explicit_coordinates_keep_existing_offset_and_override_behavior(self):
        self.write_csv(
            "Site,Subsite,Device,X,Y\nS,,,1000,2000\n,A,,100,200\n"
            ",A,D,1,2\nS,A,D,10,20\n"
        )
        result = compile_devices_csv(str(self.csv_path), raise_on_error=True)
        device = result.sites[0].subsites[0].devices[0]
        self.assertEqual((device.absolute_x, device.absolute_y), (-1110, -2220))
        self.assertEqual(len(result.overrides), 1)

    def test_blank_pairs_inherit_template_coordinates_and_merge_tags(self):
        self.write_csv(
            "Site,Subsite,Device,X,Y,Tags\n,A,,100,200,\n,A,D,1,2,template\n"
            "S,A,,,,local-subsite\nS,A,D,,,local-device\n"
        )
        result = compile_devices_csv(str(self.csv_path), raise_on_error=True)
        subsite = result.sites[0].subsites[0]
        device = subsite.devices[0]
        self.assertEqual((subsite.x, subsite.y), (-100, -200))
        self.assertEqual((device.x, device.y), (-1, -2))
        self.assertEqual((device.absolute_x, device.absolute_y), (-101, -202))
        self.assertEqual(device.tags, {"template", "local-device"})
        self.assertEqual(result.overrides, [])

    def test_duplicate_blank_pair_preserves_coordinates_in_either_order(self):
        for rows in ("S,A,D,,,tag\nS,A,D,10,20,\n", "S,A,D,10,20,\nS,A,D,,,tag\n"):
            with self.subTest(rows=rows):
                self.write_csv("Site,Subsite,Device,X,Y,Tags\n" + rows)
                result = compile_devices_csv(str(self.csv_path), raise_on_error=True)
                device = result.sites[0].subsites[0].devices[0]
                self.assertEqual((device.x, device.y), (-10, -20))
                self.assertEqual(device.tags, {"tag"})

    def test_conflict_reports_the_row_that_supplied_coordinates(self):
        self.write_csv("Site,Subsite,Device,X,Y\nS,A,D,,\nS,A,D,10,20\nS,A,D,30,40\n")
        result = compile_devices_csv(str(self.csv_path))
        self.assertTrue(result.errors[0].startswith("Rows 3 and 4:"))
