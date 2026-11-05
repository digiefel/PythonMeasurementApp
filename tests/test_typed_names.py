"""Typed site, subsite and device names work with or without a devices CSV."""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock

from config import Config
from models import Device, Site, Subsite, has_position
from tests.test_ui_connections import load_ui
from tests import test_ui_device_selection as device_tests
from tests import test_ui_site_selection as site_tests


class TypedNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_ui()

    def setUp(self):
        device_tests.DeviceSelectionTests.setUp(self)

    def type_names(self, site, subsite, devices):
        self.ui.site_cb.set(site)
        self.ui.subsite_var.set(subsite)
        self.ui.device_cb.set(devices)
        self.ui.apply_typed_names()

    def test_without_devices_csv_typed_names_run_with_unknown_positions(self):
        self.ui.config.sites = []
        self.ui.populate_sites()
        self.type_names('S1, S2', 'Cap', 'D1, D2')
        self.assertEqual(self.ui.selected_site_names, ('S1', 'S2'))
        self.assertEqual(self.ui.device_cb.get(), 'D1, D2')
        with site_tests.SiteSelectionTests.prepare_run(self):
            self.ui.run()
        queue = self.ui.runner.run_queue.call_args.args[1]
        self.assertEqual([(site.name, sub.name, device.name) for site, sub, device in queue], [
            ('S1', 'Cap', 'D1'), ('S1', 'Cap', 'D2'), ('S2', 'Cap', 'D1'), ('S2', 'Cap', 'D2'),
        ])
        self.assertFalse(any(has_position(device) for _, _, device in queue))

    def test_typed_device_in_listed_subsite_is_measured_without_asking(self):
        self.type_names('site', 'sub', 'A, new')
        queue, missing = self.ui._build_measurement_queue()
        self.assertEqual([device.name for _, _, device in queue], ['A', 'new'])
        self.assertIs(queue[0][2], self.devices[1])
        self.assertFalse(has_position(queue[1][2]))
        self.assertEqual(missing, [])

    def test_site_change_keeps_typed_names_and_replaces_picked_names(self):
        other = Site('other', [Subsite('sub2', [Device('E', 0, 0)])])
        self.ui.config.sites.append(other)
        self.ui.device_cb.set('A, typed')
        self.ui.apply_typed_names()
        self.ui.site_cb.set('other')
        self.ui.on_site_selected()
        self.assertEqual(self.ui.subsite_var.get(), 'sub2')
        self.assertEqual(self.ui.selected_device_names, ('typed',))
        self.type_names('site', 'mine', 'X')
        self.ui.site_cb.set('other')
        self.ui.on_site_selected()
        self.assertEqual(self.ui.subsite_var.get(), 'mine')
        self.assertEqual(self.ui.selected_device_names, ('X',))

    def test_typed_names_are_restored_from_saved_selection(self):
        self.type_names('S9', 'Cap', 'D1')
        saved = self.ui.build_last_selection()
        self.ui.config.sites = []
        self.ui.populate_sites()
        self.ui.apply_last_selection(saved)
        self.assertEqual((self.ui.site_cb.get(), self.ui.subsite_var.get(), self.ui.device_cb.get()),
                         ('S9', 'Cap', 'D1'))

    def test_empty_fields_do_not_start_a_run(self):
        self.type_names('', '', '')
        with site_tests.SiteSelectionTests.prepare_run(self):
            self.ui.run()
        self.ui.runner.run_queue.assert_not_called()
        self.ui.log.assert_called_with("Enter a site, subsite and device before running.")


class MissingDevicesCsvTests(unittest.TestCase):
    def test_config_starts_with_no_sites_when_csv_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            config_path = os.path.join(folder, 'global_config.json')
            with open(config_path, 'w') as f:
                json.dump({'devices_csv_path': os.path.join(folder, 'missing.csv')}, f)
            config = Config(config_path)
        self.assertEqual(config.sites, [])
        self.assertIn('File not found', config.devices_csv_error)


if __name__ == '__main__':
    unittest.main()
