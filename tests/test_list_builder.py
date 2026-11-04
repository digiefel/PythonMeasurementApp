"""Value generation behind the list builder dialog."""

import unittest

from ui_list_builder import build_values, points_for_step


class BuildValuesTests(unittest.TestCase):
    def test_linear_points_end_on_stop(self):
        self.assertEqual(build_values(0, 4, 5), [0, 1, 2, 3, 4])

    def test_linear_runs_downward(self):
        self.assertEqual(build_values(4, 0, 5), [4, 3, 2, 1, 0])

    def test_linear_step_direction_follows_start_and_stop(self):
        self.assertEqual(build_values(4, 1, 4, step=1), [4, 3, 2, 1])
        self.assertEqual(build_values(4, 1, 4, step=-1), [4, 3, 2, 1])

    def test_linear_step_that_does_not_divide_stops_short(self):
        points = points_for_step(1, 4, 0.4)
        self.assertEqual(points, 8)
        self.assertAlmostEqual(build_values(1, 4, points, step=0.4)[-1], 3.8)

    def test_points_for_step_survives_float_rounding(self):
        self.assertEqual(points_for_step(1, 4, 0.1), 31)

    def test_log_spacing_hits_every_decade(self):
        values = build_values(1e-6, 100, 25, "log")
        for decade, value in zip(range(-6, 3), values[::3]):
            self.assertAlmostEqual(value, 10.0 ** decade, delta=1e-9 * 10.0 ** decade)

    def test_log_spacing_needs_same_sign(self):
        with self.assertRaises(ValueError):
            build_values(0, 1, 5, "log")
        with self.assertRaises(ValueError):
            build_values(-1, 1, 5, "log")
        self.assertAlmostEqual(build_values(-1, -100, 3, "log")[1], -10)

    def test_single_point_is_start(self):
        self.assertEqual(build_values(2, 5, 1), [2])

    def test_rejects_bad_counts(self):
        for points in (0, -3, 10001):
            with self.assertRaises(ValueError):
                build_values(0, 1, points)
        with self.assertRaises(ValueError):
            points_for_step(0, 1, 0)


if __name__ == "__main__":
    unittest.main()
