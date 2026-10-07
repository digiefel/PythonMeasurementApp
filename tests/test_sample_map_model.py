"""Public geometry and summary behavior for progressive sample maps."""

from types import SimpleNamespace
import unittest

from data_management import Identity
from sample_map_model import build_geometry, date_text, location_summary


def item(subsite, name, x, y):
    identity = Identity('C', 'S', subsite, name)
    return SimpleNamespace(name='/'.join(identity.parts[1:]), identity=identity, x=x, y=y)


class SampleMapModelTests(unittest.TestCase):
    def test_exact_shared_coordinates_merge_members_and_subsite_outlines(self):
        a, alias, neighbor = item('FeCap', 'A1', 0, 0), item('FeCapBD', 'A1A2', 0, 0), item('FeCap', 'A2', 160, 0)
        locations, sites, subsites = build_geometry([a, alias, neighbor, item('TLM', 'R', 300, 500)])
        self.assertEqual(len(locations), 3)
        self.assertEqual(locations[0].names, {a.name, alias.name})
        self.assertEqual(len(sites), 1)
        self.assertEqual(len(subsites), 2)
        self.assertEqual(subsites[0].subsites, ('FeCap', 'FeCapBD'))
        self.assertEqual(subsites[0].bounds, (0, 0, 160, 0))

    def test_nearby_and_unpositioned_devices_are_not_merged(self):
        locations, _, _ = build_geometry([item('A', 'D', 0, 0), item('B', 'D', 0.01, 0), item('B', 'Unknown', None, None)])
        self.assertEqual(len(locations), 2)
        self.assertEqual(sum(len(location.members) for location in locations), 2)

    def test_shared_summary_combines_measurements_dates_types_notes_and_status(self):
        a, b = item('FeCap', 'A1', 0, 0), item('FeCapBD', 'A1A2', 0, 0)
        location = build_geometry([a, b])[0][0]
        annotations = {a.name: {'measurement_count': 2, 'last_measurement': '20261006_120000', 'status': 'Bad'},
                       b.name: {'measurement_count': 3, 'last_measurement': '2026-10-08T12:00:00',
                                'status': 'Good', 'has_notes': True}}
        label, count, statuses = location_summary(location, annotations)
        self.assertEqual(count, 5)
        self.assertEqual(label, 'A1, A1A2\nFeCap, FeCapBD\n2026-10-08  ▤')
        self.assertEqual(statuses, ('Bad', 'Good'))

    def test_unmeasured_devices_have_no_date_or_placeholder(self):
        a = item('TLM', 'D', 0, 0)
        label, count, _ = location_summary(build_geometry([a])[0][0], {})
        self.assertEqual(label, 'D\nTLM')
        self.assertEqual(count, 0)

    def test_duplicated_names_are_displayed_once_with_both_subsites(self):
        location = build_geometry([item('A', 'Same', 0, 0), item('B', 'Same', 0, 0)])[0][0]
        self.assertEqual(location_summary(location, {})[0], 'Same\nA, B')

    def test_dates_accept_application_and_iso_timestamps_without_fabricating_dates(self):
        for timestamp in ('20261008_120000', '2026-10-08 12:00:00', '2026-10-08T12:00:00Z', '2026-10-08'):
            self.assertEqual(date_text(timestamp), '2026-10-08')
        for timestamp in ('', 'unknown', '20260231_120000'):
            self.assertEqual(date_text(timestamp), '')


if __name__ == '__main__':
    unittest.main()
