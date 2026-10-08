"""Saved-data search behavior, independent of Tk and instruments."""

from pathlib import Path
import unittest

from data_management import Identity, Measurement
from measurement_query import Condition, MeasurementQuery, find_devices


class MeasurementQueryTests(unittest.TestCase):
    def setUp(self):
        self.identity = Identity('Chip', 'III', 'FeCap', 'A1')
        self.item = Measurement(self.identity, 'run_20261008_120000_IV', (Path('run.csv'), Path('run_plot.png')),
                                {'Procedure': 'IV Sweep', 'Timestamp': '20261008_120000', 'Temperature_C': '25.0'})
        self.annotation = {'status': 'Bad', 'notes': 'Leaky after fatigue.', 'has_notes': True}

    def query(self, *conditions, **kwargs):
        return MeasurementQuery(conditions=conditions, **kwargs).matches(self.item, self.annotation)

    def test_words_find_metadata_paths_and_notes_without_case_sensitivity(self):
        self.assertTrue(self.query(text='iv FECAP leaky'))
        self.assertFalse(self.query(text='iv other'))

    def test_conditions_can_match_all_or_any(self):
        yes, no = Condition('Procedure', 'contains', 'sweep'), Condition('Site', 'is', 'I')
        self.assertFalse(self.query(yes, no))
        self.assertTrue(self.query(yes, no, match_any=True))

    def test_date_boundaries_include_whole_days_and_accept_application_timestamps(self):
        self.assertTrue(self.query(Condition('Date', 'on or after', '2026-10-08'), Condition('Date', 'on or before', '2026-10-08')))
        self.assertFalse(self.query(Condition('Date', 'before', '2026-10-08')))
        self.assertFalse(self.query(Condition('Date', 'after', '2026-10-08')))

    def test_saved_numeric_metadata_supports_comparisons(self):
        self.assertTrue(self.query(Condition('Temperature_C', 'is', '25')))
        self.assertTrue(self.query(Condition('Temperature_C', '>=', '25')))
        self.assertFalse(self.query(Condition('Temperature_C', '<', '25')))
        self.assertFalse(self.query(Condition('Unknown', '>=', '25')))

    def test_date_range_has_inclusive_and_open_boundaries_independent_of_any_conditions(self):
        self.assertTrue(self.query(from_date='2026-10-08', to_date='2026-10-08'))
        self.assertTrue(self.query(from_date='2026-10-01'))
        self.assertTrue(self.query(to_date='2026-10-08'))
        self.assertFalse(self.query(Condition('Procedure', 'contains', 'IV'), match_any=True, to_date='2026-10-07'))
        with self.assertRaises(ValueError):
            MeasurementQuery(from_date='2026-10-09', to_date='2026-10-08').validate()

    def test_current_status_notes_plot_and_warnings_are_queryable(self):
        for field, value in (('Device status', 'Bad'), ('Notes', 'fatigue'), ('Has notes', 'Yes'),
                             ('Has plot', 'Yes'), ('Metadata warning', 'No')):
            self.assertTrue(self.query(Condition(field, 'contains', value)))
        self.annotation['status'] = ''
        self.assertTrue(self.query(Condition('Device status', 'is', 'Untagged')))

    def test_missing_values_do_not_match_exclusions_and_invalid_filters_are_rejected(self):
        self.assertFalse(self.query(Condition('Unknown', 'is not', 'anything')))
        for condition in (Condition('Date', 'is', '20260231'), Condition('Date', 'is', '2026-02-31'),
                          Condition('Temperature_C', '>', 'warm')):
            with self.assertRaises(ValueError):
                condition.validate()

    def test_name_search_prefers_exact_site_subsite_or_device_names(self):
        alias = Identity('Chip', 'II', 'FeCapBD', 'A1A2')
        self.assertEqual(find_devices([self.identity, alias], 'a1'), {self.identity})
        self.assertEqual(find_devices([self.identity, alias], 'III'), {self.identity})
        self.assertEqual(find_devices([self.identity, alias], 'fecap'), {self.identity})
        self.assertEqual(find_devices([self.identity, alias], 'ii/fecapbd'), {alias})
        self.assertEqual(find_devices([self.identity, alias], ''), set())


if __name__ == '__main__':
    unittest.main()
