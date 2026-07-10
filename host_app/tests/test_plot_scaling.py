import unittest

from aix_host_app.plot_scaling import pressure_x_range, pressure_y_range


class PressurePlotScalingTests(unittest.TestCase):
    def test_low_pressure_variation_uses_tight_readable_range(self):
        low, high = pressure_y_range([4.4, 4.8, 5.1, 5.9])

        self.assertLessEqual(low, 4.4)
        self.assertGreaterEqual(high, 5.9)
        self.assertLess(high - low, 15.0)
        self.assertGreaterEqual(high - low, 8.0)

    def test_near_zero_pressure_keeps_lower_bound_at_zero(self):
        low, high = pressure_y_range([0.3, 0.6])

        self.assertEqual(low, 0.0)
        self.assertGreaterEqual(high, 8.0)

    def test_wide_pressure_variation_gets_padding(self):
        low, high = pressure_y_range([40.0, 80.0, 120.0])

        self.assertLess(low, 40.0)
        self.assertGreater(high, 120.0)

    def test_x_range_follows_latest_sample_with_fixed_window(self):
        low, high = pressure_x_range([26000, 27000, 27526], window_points=180)

        self.assertGreater(low, 27000)
        self.assertGreaterEqual(high, 27526)
        self.assertLessEqual(high - 27526, 10)
        self.assertLess(high - low, 220)

    def test_x_range_has_readable_minimum_span_for_short_series(self):
        low, high = pressure_x_range([10, 12], min_span=60)

        self.assertEqual(low, 0)
        self.assertGreaterEqual(high, 60)


if __name__ == "__main__":
    unittest.main()
