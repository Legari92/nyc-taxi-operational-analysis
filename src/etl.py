"""Prepare 2024 yellow-taxi data for a descriptive notebook and Power BI.

Run from the project root: python src/etl.py
One source month is held in memory at a time. Monetary totals are recorded
passenger amounts, not profit. See docs/METHODOLOGY.md for source limitations.
"""
from __future__ import annotations

import argparse
from datetime import timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

YEAR = 2024
NY = "America/New_York"
EST = timezone(timedelta(hours=-5))
AIRPORT_ZONES = {1, 132, 138}
SOURCE_COLUMNS = [
    "tpep_pickup_datetime", "tpep_dropoff_datetime", "PULocationID",
    "DOLocationID", "trip_distance", "payment_type", "fare_amount",
    "tip_amount", "total_amount", "Airport_fee",
]
SUM_COLUMNS = [
    "trip_count", "total_revenue", "total_fare_amount", "total_tip_amount",
    "total_trip_distance", "total_trip_duration_min", "tipped_trip_count",
    "card_trip_count", "cash_trip_count", "flex_fare_trip_count",
    "airport_fee_missing_count", "tip_missing_count",
]
SEGMENT_KEYS = ["pickup_hour", "PULocationID", "airport_trip_share"]
WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
LEGACY_COLUMNS = [
    "pickup_hour", "PULocationID", "trip_count", "total_revenue",
    "avg_total_amount", "avg_fare_amount", "avg_tip_amount", "tip_rate",
    "avg_trip_distance", "avg_trip_duration_min", "airport_trip_share",
    "cash_trip_share", "card_trip_share", "flex_fare_share", "pickup_month",
    "pickup_dayofweek", "pickup_hour_num", "is_weekend", "temp_c", "rain_mm",
    "rain_flag", "moderate_rain_flag", "heavy_rain_flag", "visibility",
    "wind_speed", "is_dark", "pickup_borough", "pickup_zone",
    "pickup_service_zone", "pickup_weekday_name", "hour_segment",
    "pickup_borough_clean", "pickup_borough_grouped", "low_visibility_flag", "temp_bin",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_month(frame: pd.DataFrame, source_month: int):
    """Apply sequential exclusions; cross-month records remain eligible."""
    df = frame.copy()
    for name in ["tpep_pickup_datetime", "tpep_dropoff_datetime"]:
        df[name] = pd.to_datetime(df[name], errors="coerce")
    df["duration"] = (df.tpep_dropoff_datetime - df.tpep_pickup_datetime).dt.total_seconds() / 60
    audit = []

    def keep(rule, mask):
        nonlocal df
        before = len(df)
        df = df.loc[mask.fillna(False)].copy()
        audit.append({"source_month": source_month, "rule": rule,
                      "rows_before": before, "rows_removed": before - len(df),
                      "rows_after": len(df)})

    keep("pickup_in_2024", df.tpep_pickup_datetime.ge("2024-01-01") & df.tpep_pickup_datetime.lt("2025-01-01"))
    keep("positive_location_ids", df.PULocationID.gt(0) & df.DOLocationID.gt(0))
    keep("distance_0_to_100_miles", df.trip_distance.gt(0) & df.trip_distance.le(100))
    keep("fare_0_to_500_usd", df.fare_amount.gt(0) & df.fare_amount.le(500))
    keep("total_0_to_500_usd", df.total_amount.gt(0) & df.total_amount.le(500))
    keep("duration_0_to_180_minutes", df.duration.gt(0) & df.duration.le(180))
    quality = {"source_month": source_month, "raw_trips": len(frame), "clean_trips": len(df),
               "valid_trips_outside_source_month": int(df.tpep_pickup_datetime.dt.month.ne(source_month).sum()),
               "airport_fee_missing_count": int(df.Airport_fee.isna().sum()),
               "tip_missing_count": int(df.tip_amount.isna().sum())}
    df["pickup_hour"] = df.tpep_pickup_datetime.dt.floor("h")
    # Positive recorded fee is a distinct segment. Missing values are audited,
    # and the other segment is labelled 'without a positive recorded fee'.
    df["airport_trip_share"] = df.Airport_fee.gt(0).astype("int8")
    for name, mask in {
        "tipped_trip_count": df.tip_amount.gt(0),
        "card_trip_count": df.payment_type.eq(1),
        "cash_trip_count": df.payment_type.eq(2),
        "flex_fare_trip_count": df.payment_type.eq(0),
        "airport_fee_missing_count": df.Airport_fee.isna(),
        "tip_missing_count": df.tip_amount.isna(),
    }.items():
        df[name] = mask.astype("int8")
    aggregations = {
        "trip_count": ("total_amount", "size"),
        "total_revenue": ("total_amount", "sum"),
        "total_fare_amount": ("fare_amount", "sum"),
        "total_tip_amount": ("tip_amount", "sum"),
        "total_trip_distance": ("trip_distance", "sum"),
        "total_trip_duration_min": ("duration", "sum"),
        **{name: (name, "sum") for name in SUM_COLUMNS[6:]},
    }
    grouped = df.groupby(SEGMENT_KEYS, as_index=False, observed=True).agg(**aggregations)
    return grouped, audit, quality


def make_calendar() -> pd.DataFrame:
    """8784 civil-clock labels; real-hour exposure is 0/2 at DST changes."""
    utc = pd.date_range("2024-01-01", "2025-01-01", freq="h", inclusive="left", tz=NY).tz_convert("UTC")
    local = utc.tz_convert(NY).tz_localize(None)
    slots = pd.DataFrame({"pickup_hour": local, "utc": utc})
    exposure = slots.groupby("pickup_hour").agg(elapsed_hours=("utc", "size"), utc=("utc", "first"))
    calendar = pd.DataFrame({"pickup_hour": pd.date_range("2024-01-01", "2025-01-01", freq="h", inclusive="left")})
    calendar = calendar.merge(exposure, on="pickup_hour", how="left", validate="one_to_one")
    calendar["elapsed_hours"] = calendar.elapsed_hours.fillna(0).astype("int8")
    calendar["dst_ambiguous"] = calendar.elapsed_hours.eq(2).astype("int8")
    calendar["pickup_month"] = calendar.pickup_hour.dt.month
    calendar["pickup_dayofweek"] = calendar.pickup_hour.dt.dayofweek
    calendar["pickup_hour_num"] = calendar.pickup_hour.dt.hour
    calendar["is_weekend"] = calendar.pickup_dayofweek.ge(5).astype("int8")
    calendar["pickup_weekday_name"] = calendar.pickup_dayofweek.map(dict(enumerate(WEEKDAYS)))
    calendar["hour_segment_order"] = calendar.pickup_hour_num // 6
    calendar["hour_segment"] = calendar.hour_segment_order.map({0: "Madrugada", 1: "Mañana", 2: "Tarde", 3: "Noche"})
    return calendar


def prepare_weather(path: Path, calendar: pd.DataFrame):
    """Use one routine FM-15 report per standard-clock hour; preserve unknowns.

    Precipitation covers the preceding hour ending at the observation time,
    normally :51. Assigning it to that clock-hour bin is an approximation.
    FM-16 special reports overlap these intervals and are not independent hours.
    """
    raw = pd.read_csv(path, low_memory=False)
    if set(raw.STATION.dropna()) != {"USW00094728"}:
        raise ValueError("Expected the documented Central Park station USW00094728")
    raw["stamp"] = pd.to_datetime(raw.DATE, errors="raise")
    daily = raw.loc[raw.REPORT_TYPE.eq("SOD"), ["stamp", "Sunrise", "Sunset"]].copy()
    daily["standard_date"] = daily.stamp.dt.normalize()
    if daily.standard_date.duplicated().any():
        raise ValueError("Duplicate daily sunrise/sunset records")
    wx = raw.loc[raw.REPORT_TYPE.eq("FM-15")].sort_values("stamp").copy()
    # This source CSV has ten incorrect DATE labels near DST transitions.
    # Its raw METAR remarks retain the UTC day/hour/minute of each observation.
    # Resolve that day against the adjacent dates; fail if it cannot be verified.
    clock = wx.REM.astype("string").str.extract(r"\b(\d{2})(\d{2})(\d{2})Z\b").astype("Int64")
    reference = wx.stamp + pd.Timedelta(hours=5)
    utc_stamp = pd.Series(pd.NaT, index=wx.index, dtype="datetime64[ns]")
    for shift in [-1, 0, 1]:
        day = reference.dt.normalize() + pd.Timedelta(days=shift)
        candidate = day + pd.to_timedelta(clock[1].astype(float), unit="h") + pd.to_timedelta(clock[2].astype(float), unit="m")
        valid = day.dt.day.eq(clock[0]) & (candidate - reference).abs().le(pd.Timedelta(hours=2))
        utc_stamp.loc[valid.fillna(False)] = candidate.loc[valid.fillna(False)]
    if utc_stamp.isna().any() or utc_stamp.dt.floor("h").duplicated().any():
        raise ValueError("Routine METAR UTC clocks must resolve to unique hours")
    corrected = utc_stamp.ne(reference)
    corrections = [{"source_DATE": wx.loc[i, "DATE"], "verified_UTC": utc_stamp.loc[i].isoformat() + "Z"}
                   for i in wx.index[corrected]]
    precip = wx.HourlyPrecipitation.astype("string").str.strip()
    wx["trace_precipitation"] = precip.eq("T").fillna(False).astype("int8")
    wx["rain_mm"] = pd.to_numeric(precip.mask(precip.eq("T").fillna(False), "0"), errors="coerce")
    wx["precipitation_known"] = wx.rain_mm.notna().astype("int8")
    unparsed_precipitation = int((precip.notna() & wx.rain_mm.isna()).sum())
    for old, new in [("HourlyDryBulbTemperature", "temp_c"), ("HourlyVisibility", "visibility"), ("HourlyWindSpeed", "wind_speed")]:
        wx[new] = pd.to_numeric(wx[old], errors="coerce")
    wx["pickup_hour"] = utc_stamp.dt.tz_localize("UTC").dt.floor("h").dt.tz_convert(NY).dt.tz_localize(None)
    # Fall-back clock hour cannot be assigned to the individual taxi occurrence.
    ambiguous_labels = calendar.loc[calendar.dst_ambiguous.eq(1), "pickup_hour"]
    wx = wx.loc[~wx.pickup_hour.isin(ambiguous_labels)].copy()
    fields = ["pickup_hour", "rain_mm", "trace_precipitation", "precipitation_known", "temp_c", "visibility", "wind_speed"]
    result = calendar.merge(wx[fields], on="pickup_hour", how="left", validate="one_to_one")
    result["precipitation_known"] = result.precipitation_known.fillna(0).astype("int8")
    result["precipitation_category"] = "Desconocida"
    known = result.precipitation_known.eq(1)
    result.loc[known, "precipitation_category"] = np.select(
        [result.loc[known, "rain_mm"].ge(10), result.loc[known, "rain_mm"].ge(2.5),
         result.loc[known, "rain_mm"].gt(0), result.loc[known, "trace_precipitation"].eq(1)],
        ["Intensa", "Moderada", "Ligera", "Traza"], default="Sin precipitación")
    for name, mask in {
        "rain_flag": result.rain_mm.gt(0) | result.trace_precipitation.eq(1),
        "moderate_rain_flag": result.rain_mm.ge(2.5),
        "heavy_rain_flag": result.rain_mm.ge(10),
    }.items():
        result[name] = mask.astype("Int8").where(known)
    result["low_visibility_flag"] = result.visibility.lt(1).astype("Int8").where(result.visibility.notna())
    result["temp_bin"] = pd.cut(result.temp_c, [-np.inf, 0, 10, 20, 30, np.inf], right=False,
                                 labels=["<0 °C", "0–<10 °C", "10–<20 °C", "20–<30 °C", "≥30 °C"])
    midpoint_standard = (result.utc + pd.Timedelta(minutes=30)).dt.tz_convert(EST).dt.tz_localize(None)
    result["standard_date"] = midpoint_standard.dt.normalize()
    result = result.merge(daily[["standard_date", "Sunrise", "Sunset"]], on="standard_date", how="left", validate="many_to_one")
    sun = {}
    for name in ["Sunrise", "Sunset"]:
        value = pd.to_numeric(result[name], errors="coerce")
        sun[name] = (value // 100) * 60 + value % 100
    minute = midpoint_standard.dt.hour * 60 + midpoint_standard.dt.minute
    usable = result.elapsed_hours.eq(1) & sun["Sunrise"].notna() & sun["Sunset"].notna()
    result["is_dark"] = (minute.lt(sun["Sunrise"]) | minute.ge(sun["Sunset"])).astype("Int8").where(usable)
    result = result.drop(columns=["utc", "standard_date", "Sunrise", "Sunset"])
    report = {"raw_weather_rows": len(raw), "routine_reports": int(raw.REPORT_TYPE.eq("FM-15").sum()),
              "trace_routine_reports": int(precip.eq("T").sum()),
              "unparsed_routine_precipitation": unparsed_precipitation,
              "weather_DATE_corrections": corrections,
              "weather_unknown_clock_bins": int((~known & result.elapsed_hours.gt(0)).sum()),
              "maximum_precipitation_mm": float(result.rain_mm.max())}
    return result, report


def add_averages(df):
    for name, numerator in {
        "avg_total_amount": "total_revenue", "avg_fare_amount": "total_fare_amount",
        "avg_tip_amount": "total_tip_amount", "avg_trip_distance": "total_trip_distance",
        "avg_trip_duration_min": "total_trip_duration_min", "tip_rate": "tipped_trip_count",
        "cash_trip_share": "cash_trip_count", "card_trip_share": "card_trip_count",
        "flex_fare_share": "flex_fare_trip_count",
    }.items():
        df[name] = df[numerator].div(df.trip_count.where(df.trip_count.ne(0)))
    return df


def run(taxi_dir: Path, weather_file: Path, zone_file: Path, output: Path):
    files = [taxi_dir / f"yellow_tripdata_2024-{month:02}.parquet" for month in range(1, 13)]
    missing = [p.name for p in files if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"A full-year run needs all 12 source files. Missing: {missing}")
    output.mkdir(parents=True, exist_ok=True)
    parts, audit, quality, sources = [], [], [], []
    for month, path in enumerate(files, 1):
        grouped, rules, month_quality = clean_month(pd.read_parquet(path, columns=SOURCE_COLUMNS), month)
        parts.append(grouped)
        audit.extend(rules)
        quality.append(month_quality)
        sources.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
        print(f"Month {month:02}: {month_quality['raw_trips']:,} raw; {month_quality['clean_trips']:,} clean", flush=True)
    # Cross-month records can have the same hour-zone-segment key: sum again.
    fact = pd.concat(parts, ignore_index=True).groupby(SEGMENT_KEYS, as_index=False)[SUM_COLUMNS].sum()
    del parts
    zones = pd.read_csv(zone_file).rename(columns={"LocationID": "PULocationID", "Borough": "pickup_borough",
                      "Zone": "pickup_zone", "service_zone": "pickup_service_zone"})
    if zones.PULocationID.duplicated().any():
        raise ValueError("Zone lookup keys must be unique")
    fact = fact.merge(zones, on="PULocationID", how="left", validate="many_to_one")
    for col in ["pickup_borough", "pickup_zone", "pickup_service_zone"]:
        fact[col] = fact[col].fillna("Unknown")
    fact["pickup_borough_clean"] = fact.pickup_borough.replace({"EWR": "Newark", "N/A": "Unknown"})
    fact["pickup_borough_grouped"] = fact.pickup_borough_clean
    fact["airport_pickup"] = fact.PULocationID.isin(AIRPORT_ZONES).astype("int8")
    calendar, weather_report = prepare_weather(weather_file, make_calendar())
    fact = fact.merge(calendar, on="pickup_hour", how="left", validate="many_to_one")
    if fact.elapsed_hours.isna().any() or (fact.elapsed_hours.eq(0) & fact.trip_count.gt(0)).any():
        raise ValueError("Observed pickups in nonexistent or unmapped local hours; investigate before export")
    fact = add_averages(fact)
    system = fact.groupby("pickup_hour", as_index=False)[SUM_COLUMNS].sum()
    for label, mask in {"airport_surcharge": fact.airport_trip_share.eq(1), "airport_pickup": fact.airport_pickup.eq(1)}.items():
        selected = fact.loc[mask].groupby("pickup_hour")[["trip_count", "total_revenue"]].sum().add_prefix(label + "_")
        system = system.merge(selected, on="pickup_hour", how="left", validate="one_to_one")
    system = calendar.merge(system, on="pickup_hour", how="left", validate="one_to_one")
    metrics = SUM_COLUMNS + [f"{a}_{b}" for a in ["airport_surcharge", "airport_pickup"] for b in ["trip_count", "total_revenue"]]
    system[metrics] = system[metrics].fillna(0)
    system = add_averages(system)
    assert int(fact.trip_count.sum()) == sum(q["clean_trips"] for q in quality)
    assert int(system.trip_count.sum()) == int(fact.trip_count.sum())
    np.testing.assert_allclose(system.total_revenue.sum(), fact.total_revenue.sum(), rtol=0, atol=0.01)
    assert not fact.duplicated(SEGMENT_KEYS).any()
    assert int(calendar.elapsed_hours.sum()) == 8784
    assert calendar.loc[calendar.precipitation_known.eq(0), "rain_mm"].isna().all()
    matrix = fact.groupby(["airport_pickup", "airport_trip_share"], as_index=False)[["trip_count", "total_revenue"]].sum()
    audit_df, quality_df = pd.DataFrame(audit), pd.DataFrame(quality)
    assert audit_df.rows_removed.sum() + fact.trip_count.sum() == quality_df.raw_trips.sum()
    kpis = {"raw_trips": int(quality_df.raw_trips.sum()), "clean_trips": int(fact.trip_count.sum()),
            "recorded_total_usd": round(float(fact.total_revenue.sum()), 2),
            "avg_recorded_total_usd": float(fact.total_revenue.sum() / fact.trip_count.sum()),
            "avg_distance_miles": float(fact.total_trip_distance.sum() / fact.trip_count.sum()),
            "avg_recorded_duration_min": float(fact.total_trip_duration_min.sum() / fact.trip_count.sum()),
            "airport_surcharge_trips": int(fact.loc[fact.airport_trip_share.eq(1), "trip_count"].sum()),
            "airport_pickup_trips": int(fact.loc[fact.airport_pickup.eq(1), "trip_count"].sum()),
            "valid_cross_month_trips_retained": int(quality_df.valid_trips_outside_source_month.sum()),
            "real_hours": int(calendar.elapsed_hours.sum()), "observed_clock_hours": fact.pickup_hour.nunique(),
            "fact_rows": len(fact), **weather_report}
    fact.to_parquet(output / "taxi_fact_2024.parquet", index=False)
    # First 35 columns retain the original schema; new model fields follow.
    ordered = LEGACY_COLUMNS + [c for c in fact.columns if c not in LEGACY_COLUMNS]
    fact[ordered].to_csv(output / "taxi_analysis_2024_final.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    for name, frame in [("taxi_hourly_system_2024", system), ("dim_hour_2024", calendar),
                        ("cleaning_audit_2024", audit_df), ("source_quality_2024", quality_df),
                        ("airport_reconciliation_2024", matrix)]:
        frame.to_csv(output / f"{name}.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    sources.extend({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in [weather_file, zone_file])
    (output / "validation_summary.json").write_text(json.dumps(kpis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "source_manifest.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(kpis, ensure_ascii=False, indent=2), flush=True)
    return kpis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxi-dir", type=Path, default=Path("data/raw/taxi"))
    parser.add_argument("--weather-file", type=Path, default=Path("data/raw/weather/LCD_USW00094728_2024.csv"))
    parser.add_argument("--zone-file", type=Path, default=Path("data/raw/zones/taxi_zone_lookup.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    run(args.taxi_dir, args.weather_file, args.zone_file, args.output)
