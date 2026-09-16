"""Small hand-calculated examples for the new comparison logic."""
import unittest

import pandas as pd

from scripts.analyze_operational_questions import borough_comparison, monthly_comparison, window_masks


class OperationalQuestionTests(unittest.TestCase):
    def test_airport_mix_uses_trip_weights_and_keeps_missing_subset_missing(self):
        source = pd.DataFrame({
            "pickup_borough_grouped": ["A", "A", "B"],
            "airport_pickup": [0, 1, 1],
            "trip_count": [3, 1, 2],
            "total_revenue": [30., 90., 80.],
        })
        result = borough_comparison(source).set_index("pickup_borough_grouped")
        self.assertEqual(result.loc["A", "mean_usd"], 30.)
        self.assertEqual(result.loc["A", "non_airport_mean_usd"], 10.)
        self.assertEqual(result.loc["A", "airport_trip_share"], .25)
        self.assertTrue(pd.isna(result.loc["B", "non_airport_mean_usd"]))

    def test_common_weekday_mix_removes_only_composition_difference(self):
        source = pd.DataFrame({
            "pickup_month": [1, 1, 2, 2],
            "pickup_dayofweek": [0, 1, 0, 1],
            "trip_count": [20, 20, 10, 40],
            "elapsed_hours": [2, 1, 1, 2],
        })
        result, _ = monthly_comparison(source)
        self.assertAlmostEqual(result.loc[0, "observed_trips_per_hour"], 40 / 3)
        self.assertAlmostEqual(result.loc[1, "observed_trips_per_hour"], 50 / 3)
        self.assertEqual(result.standardized_trips_per_hour.tolist(), [15., 15.])

    def test_weekend_nights_cross_midnight_with_exclusive_end(self):
        source = pd.DataFrame({
            "pickup_dayofweek": [4, 4, 5, 5, 6, 6, 0, 0, 0],
            "pickup_hour_num": [1, 20, 2, 3, 2, 3, 1, 7, 10],
        })
        masks = window_masks(source)
        self.assertEqual(masks["Weekend nights"].tolist(), [False, True, True, False, True, False, False, False, False])
        self.assertEqual(masks["Weekday mornings"].tolist(), [False, False, False, False, False, False, False, True, False])


if __name__ == "__main__":
    unittest.main()
