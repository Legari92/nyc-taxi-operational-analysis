# Methodology

## Sources and reproducible version

The analysis reuses the original project's source files at commit `b3bdf9d213cda1efcd5477cb505cb47f422532b8`. The [source manifest](../data/processed/source_manifest.json) records each input's size and SHA-256.

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page): twelve 2024 yellow taxi files. Monthly URL pattern: `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-MM.parquet`.
- [Yellow Taxi dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf): the original project's [dictionary copy](data_dictionary_trip_records_yellow.pdf) is included.
- [Taxi Zone Lookup](https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv): the reviewed copy is included in `data/raw/zones/`.
- [NOAA Local Climatological Data](https://www.ncei.noaa.gov/products/land-based-station/local-climatological-data): Central Park station **USW00094728**, 2024. The reviewed weather CSV is included in `data/raw/weather/`.
- [LCDv2 documentation](https://www.ncei.noaa.gov/oa/local-climatological-data/v2/doc/lcdv2_DOCUMENTATION.pdf) and [National Weather Service METAR reference](https://www.weather.gov/asos/METAR.html): units, observation timing and UTC timestamps.

`python scripts/download_data.py` downloads the taxi snapshot from the pinned original commit. `--source tlc` tries the official URLs but still requires the same hashes. Changed or mismatched files cause a failure instead of silently mixing source versions.

## Population and exclusions

The original unit is a completed yellow taxi trip record. Rules run in sequence, and each exclusion is counted once:

1. Pickup from January 1, 2024 inclusive to January 1, 2025 exclusive.
2. Positive pickup and drop-off location IDs.
3. Distance greater than 0 and at most 100 miles.
4. Fare amount greater than 0 and at most $500.
5. Total amount greater than 0 and at most $500.
6. Recorded duration greater than 0 and at most 180 minutes.

These thresholds preserve comparability with the original analysis. They can exclude real outliers and do not guarantee that every retained record is correct. Unrecognized location IDs remain Unknown.

All twelve files are required and processed sequentially. **352 valid 2024 records whose pickup month differs from their source filename are retained.** A month mismatch does not establish duplication. No deduplication is attempted without a reliable key, so possible source duplicates remain a limitation.

The [cleaning audit](../data/processed/cleaning_audit_2024.csv) reconciles **41,169,720 source records** to **39,677,878 retained trips**.

## Aggregation and measures

The fact table has one row per **local pickup hour × pickup zone × positive-surcharge indicator**. Splitting that indicator before aggregation avoids classifying every trip in a mixed group as airport-related. Airport pickup location remains a separate classification.

Means divide additive sums by trip counts. For example, average recorded amount is `SUM(total_revenue) / SUM(trip_count)`, not an unweighted mean of grouped averages. The CSV retains the original 35 columns first and adds 17 fields; Power Query accepts all 52 columns.

| Field | Definition |
|---|---|
| `total_revenue` | Legacy technical name for recorded total amount; not profit or driver net income |
| `airport_trip_share` | 0 or 1 at the fact grain, based on `Airport_fee > 0` |
| `airport_pickup` | Pickup zones 1, 132 or 138: Newark, JFK or LaGuardia |
| `airport_fee_missing_count` | Missing fee records: 3,692,098 retained trips; included without a positive recorded fee |
| `tip_rate` | Fraction of trips with a positive recorded tip; not the monetary tip percentage |

TLC does not record cash tips. The [airport reconciliation](../data/processed/airport_reconciliation_2024.csv) keeps airport pickup and positive recorded surcharge distinct.

## Calendar and clock changes

Taxi timestamps represent New York local clock time. The repeated autumn hour cannot be assigned to either occurrence at trip level. Its grouped count is preserved and the calendar assigns **two real hours** of exposure. The spring gap has zero exposure. The year contains **8,784 real hours** and **8,783 observed taxi clock-hour labels**.

Hourly activity is `SUM(trip_count) / SUM(DimHora[elapsed_hours])`. The hour dimension filters the fact table in one direction. Time and weather axes come from that dimension; location and segment filters do not remove zero-trip hours from the denominator.

Recorded duration subtracts the source clock timestamps. Trips crossing a clock change can therefore have inaccurate durations; the analysis does not invent an ordering to resolve ambiguous timestamps.

## Weather and light context

The LCDv2 file already uses millimetres, Celsius, kilometres of visibility and metres per second of wind. The ETL uses **8,767 routine FM-15 reports**, one per UTC hour. Special FM-16 reports are excluded to avoid overlapping precipitation intervals and weighting by reporting frequency.

For ten records near clock changes, `DATE` disagrees with the UTC timestamp in the original METAR `REM` field. The ETL reconstructs UTC from DDHHMMZ using adjacent candidate dates, requires every timestamp to resolve and checks UTC uniqueness. Those corrections are recorded in [validation_summary.json](../data/processed/validation_summary.json), before conversion to `America/New_York`.

Precipitation describes the preceding 60 minutes, usually observed at :51. It is assigned to the containing clock-hour group, approximately nine minutes offset from a full clock hour. Trace values remain a separate category, with numeric zero as a measurement-limit representation. Missing or uninterpretable values remain unknown.

**82 real hours** lack a known precipitation category, including the ambiguous autumn hour with two hours of exposure. Only **17 hours** have precipitation of at least 10 mm. Small groups and one weather station limit interpretation; these comparisons do not control for calendar composition or vehicle supply.

Sunrise and sunset use fixed standard time, UTC-5. The midpoint of each hour is compared in that reference; ambiguous hours or missing sun data remain unknown. Grouped hour-zone rows are not treated as independent observations for significance tests. Weather and light are descriptive context, not evidence of causal effects.

## Additional comparisons and validation

The [three analytical comparisons](ANALYTICAL_FINDINGS.md) use the same inputs: airport composition, monthly rates standardized to the annual weekday mix, and zone rankings for explicitly defined morning/night windows. Their supporting tables and limitations are documented alongside the findings.

Recorded validation includes three ETL regression tests, a full-year run with exclusion and aggregate reconciliation, an independent DuckDB calculation over the raw files, all eleven notebook code cells, three analytical tests and 28 city-hour checks. Monetary reconciliation allows $0.01 total tolerance; counts are exact. The notebook ran in a fresh in-process kernel because separate Jupyter startup was blocked in that execution environment; the Jupyter interface was not tested.

The Power BI model passed all twelve baseline and 81 analytical DAX checks after refreshing the translated hour dimension on September 16, and the refreshed model was saved. All four pages of the English Desktop PDF passed visual review. Label translation preserves source files, measures and relationships. Overview filtering to Queens plus August was confirmed from a screenshot; the owner confirmed clearing restored the annual total. Other chart interactions were not manually tested. See [Power BI setup and validation](../powerbi/IMPLEMENTATION.md) and the evidence linked from the [README](../README.md).
