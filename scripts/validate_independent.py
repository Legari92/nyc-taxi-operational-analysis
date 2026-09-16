"""Independent SQL reconciliation against raw records (optional DuckDB install).

python -m pip install duckdb
python scripts/validate_independent.py --taxi-dir data/raw/taxi
"""
import argparse
import json
from pathlib import Path
import duckdb

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--taxi-dir", type=Path, default=Path("data/raw/taxi"))
args = parser.parse_args()
connection = duckdb.connect()
connection.execute("SET memory_limit='1GB'")
connection.execute("SET threads=2")
paths = [str(args.taxi_dir / f"yellow_tripdata_2024-{m:02}.parquet") for m in range(1,13)]
query = """
WITH records AS (
 SELECT *, epoch(tpep_dropoff_datetime - tpep_pickup_datetime) / 60.0 AS duration
 FROM read_parquet(?, union_by_name=true)
), cleaned AS (
 SELECT * FROM records
 WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-01'
 AND tpep_pickup_datetime < TIMESTAMP '2025-01-01'
 AND PULocationID > 0 AND DOLocationID > 0
 AND trip_distance > 0 AND trip_distance <= 100
 AND fare_amount > 0 AND fare_amount <= 500
 AND total_amount > 0 AND total_amount <= 500
 AND duration > 0 AND duration <= 180
)
SELECT count(*) AS clean_trips, sum(total_amount) AS recorded_total_usd,
 sum(trip_distance)/count(*) AS avg_distance_miles,
 sum(duration)/count(*) AS avg_recorded_duration_min,
 count(*) FILTER (WHERE Airport_fee > 0) AS airport_surcharge_trips,
 count(*) FILTER (WHERE PULocationID IN (1,132,138)) AS airport_pickup_trips
FROM cleaned
"""
result = connection.execute(query, [paths]).fetchdf().iloc[0].to_dict()
expected = json.loads(Path("data/processed/validation_summary.json").read_text())
for name, value in result.items():
    tolerance = .01 if name == "recorded_total_usd" else (1e-8 if name.startswith("avg_") else 0)
    if abs(value - expected[name]) > tolerance:
        raise AssertionError(f"{name}: raw SQL {value} differs from ETL {expected[name]}")
report = {"status": "passed", "method": "DuckDB aggregate directly from all twelve raw files", "raw_reference": result}
Path("data/processed/independent_validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
