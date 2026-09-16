"""Small regression checks for the errors found during review."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etl import clean_month, make_calendar, prepare_weather


class CleaningTests(unittest.TestCase):
    def test_mixed_airport_group_and_cross_month_record(self):
        base = dict(tpep_pickup_datetime="2024-02-01 10:00:00",
                    tpep_dropoff_datetime="2024-02-01 10:20:00", PULocationID=132,
                    DOLocationID=50, trip_distance=5, payment_type=1,
                    fare_amount=20., tip_amount=2., total_amount=25., Airport_fee=1.75)
        rows = [base, {**base, "Airport_fee": 0., "total_amount": 40.},
                {**base, "Airport_fee": np.nan, "tip_amount": np.nan},
                {**base, "trip_distance": 0}]
        grouped, audit, quality = clean_month(pd.DataFrame(rows), 1)
        self.assertEqual(grouped.trip_count.sum(), 3)
        self.assertEqual(quality["valid_trips_outside_source_month"], 3)
        self.assertEqual(grouped.loc[grouped.airport_trip_share.eq(1), "trip_count"].sum(), 1)
        self.assertEqual(grouped.total_revenue.sum(), 90.)
        self.assertEqual(grouped.airport_fee_missing_count.sum(), 1)
        self.assertEqual(sum(a["rows_removed"] for a in audit), 1)


class WeatherTests(unittest.TestCase):
    def test_calendar_exposure(self):
        c = make_calendar().set_index("pickup_hour")
        self.assertEqual(c.elapsed_hours.sum(), 8784)
        self.assertEqual(c.loc["2024-03-10 02:00:00", "elapsed_hours"], 0)
        self.assertEqual(c.loc["2024-11-03 01:00:00", "elapsed_hours"], 2)

    def test_unknown_trace_units_and_summer_alignment(self):
        rows = []
        for stamp, precip, rem in [
            ("2024-07-01T00:51:00", "", "METAR KNYC 010551Z"),
            ("2024-07-01T01:51:00", "T", "METAR KNYC 010651Z"),
            ("2024-07-01T02:51:00", "12.5", "METAR KNYC 010751Z"),
            ("2024-03-09T21:51:00", "9.7", "METAR KNYC 100351Z"),
        ]:
            rows.append(dict(STATION="USW00094728", DATE=stamp, REPORT_TYPE="FM-15",
                             REM=rem, HourlyPrecipitation=precip, HourlyDryBulbTemperature=20,
                             HourlyVisibility=16, HourlyWindSpeed=2, Sunrise=np.nan, Sunset=np.nan))
        rows.append(dict(STATION="USW00094728", DATE="2024-07-01T00:00:00", REPORT_TYPE="SOD", Sunrise=428, Sunset=1931))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weather.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            w, report = prepare_weather(path, make_calendar())
        w = w.set_index("pickup_hour")
        self.assertTrue(pd.isna(w.loc["2024-07-01 01:00:00", "rain_mm"]))
        self.assertTrue(pd.isna(w.loc["2024-07-01 01:00:00", "rain_flag"]))
        self.assertEqual(w.loc["2024-07-01 02:00:00", "precipitation_category"], "Traza")
        self.assertEqual(w.loc["2024-07-01 03:00:00", "rain_mm"], 12.5)
        self.assertEqual(w.loc["2024-07-01 04:00:00", "is_dark"], 1)
        self.assertEqual(w.loc["2024-07-01 05:00:00", "is_dark"], 0)
        self.assertEqual(w.loc["2024-03-09 22:00:00", "rain_mm"], 9.7)
        self.assertEqual(len(report["weather_DATE_corrections"]), 1)
        self.assertTrue(pd.isna(w.loc["2024-11-03 01:00:00", "is_dark"]))


if __name__ == "__main__":
    unittest.main()
