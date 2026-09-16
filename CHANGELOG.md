# Changelog

This project evolves in the same repository. Entries describe changes to the analysis and its evidence, rather than treating each update as a separate project.

## v2 - 2026-09-16

### Analysis

- Corrected hourly activity to divide trips by real calendar hours, including zero-trip hours and daylight-saving transitions. The annual rate is 4,517.06 trips per real hour.
- Separated airport pickup locations from positive recorded airport fees, and made missing-fee and recorded-amount limitations explicit.
- Added three comparisons: airport composition in borough averages, monthly activity with a common weekday mix, and pickup-zone rankings for weekday mornings versus Friday/Saturday nights.
- Retained the original 2024 sources and the already-correct annual total of **39,677,878 trips**. These are descriptive comparisons; no forecasting, causal effects or profitability claims were added.

### Report and reproducibility

- Replaced the previous PBIX in the current repository tree with editable Power BI project files, an English four-page PDF and reviewed previews.
- Standardized the README, notebook, analysis figures and visible dashboard text in English. Existing technical identifiers remain where needed to preserve model references.
- Added reproducible download and ETL scripts, source checksums, setup instructions and documented metric definitions.
- Removed large raw taxi files from the current tree. The downloader uses the pinned original snapshot, which remains in Git history. CSV files preserve their bytes across platforms for checksum validation.

### Validation

- Independent SQL and ETL agree on the retained trip total and reviewed aggregate amounts.
- All **6 Python tests**, **11 notebook code cells**, and **93 Power BI DAX checks** passed.
- All four pages of the English Desktop PDF passed visual review.
- The Queens/August Overview filter was confirmed from a screenshot; resetting to the annual total was confirmed by the owner. Other chart interactions were not manually tested.

See the [analysis findings](docs/ANALYTICAL_FINDINGS.md), [validation evidence](README.md#validation) and [Power BI guide](powerbi/IMPLEMENTATION.md).

## Original baseline - 2026-05-02

The original project combined 2024 NYC yellow taxi trips and weather data in an executed notebook and a four-page Power BI dashboard. It covered temporal patterns, pickup geography and operational segments.

The [original repository snapshot](https://github.com/Legari92/nyc-taxi-operational-analysis/tree/b3bdf9d213cda1efcd5477cb505cb47f422532b8) remains available in Git history, including its PBIX and raw inputs. v2 continues that project with corrected definitions, additional comparisons and stronger validation.
