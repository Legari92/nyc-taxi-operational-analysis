# Power BI setup and validation

The current editable report is `dashboard/NYC Taxi v2.pbip`, together with its `.Report` and `.SemanticModel` folders. It contains four pages and 22 measures across five tables. The report text and category labels have been translated to English. The translated hour dimension has been refreshed and saved, and all 93 DAX checks passed on September 16. All four pages of the English Desktop export passed visual review; the PDF and its previews are included.

## Open a fresh checkout

1. Follow the Python setup in the [README](../README.md) and run the downloader and ETL from the project root. The ETL generates `data/processed/taxi_analysis_2024_final.csv` and `data/processed/dim_hour_2024.csv`, the two Power BI inputs.
2. Open `dashboard/NYC Taxi v2.pbip` in Power BI Desktop. Keep both adjacent project folders in place.
3. In Power Query, edit the text parameter **ProjectRoot** to your checkout's absolute root, for example `C:/Projects/nyc-taxi-operational-analysis`. The publication copy contains a placeholder. If opening first reports a missing source, configure the parameter before retrying refresh.
4. Apply changes, refresh and save. Git excludes the model's local data cache, so a new checkout must import the generated data before displaying the interactive report.

Microsoft's [Power BI project documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview) describes PBIP. The saved TMDL/PBIR definitions are the source of truth for this report. The `.pq` and `.dax` files in this folder are readable calculation references. Legacy technical identifiers are retained; visible aliases and category values are in English. Label conversion happens after CSV import, so the reviewed source files remain unchanged.

## Model choices

- The fact grain is local pickup hour × pickup zone × positive-surcharge indicator. The CSV has 52 columns; its Power Query import does not assume the former 35-column schema.
- `DimHora` filters the fact table through an active one-to-many, single-direction relationship on `pickup_hour`. Temporal and weather axes use this dimension.
- Period hours come from the complete calendar. A zone or surcharge filter must not reduce the denominator to hours with observed trips. The calendar includes zero exposure for the spring clock gap and two hours for the repeated autumn label.
- Means divide additive sums by trip counts. `total_revenue` is the legacy technical name for recorded total amount, not profit or driver net income.
- Airport pickup uses zones 1, 132 and 138. Positive recorded airport surcharge is a separate indicator. Missing fees belong to the group without a positive recorded fee, not a claim that no fee was charged.
- Analytical pages keep chart comparisons independent: selecting a chart does not cross-filter the other comparisons. Slicers still apply. Overview retains chart interactions. Notes labelled `2024 annual reference` remain annual context when filters change.

The [analytical findings](../docs/ANALYTICAL_FINDINGS.md) explain the airport comparison, weekday standardization and morning/night windows.

## Repeat the numerical checks

Run [validate_report.dax](validate_report.dax) and [validate_analytical_findings.dax](validate_analytical_findings.dax) in Desktop's DAX query view. These are read-only queries; each returned `Pass` value should be TRUE. The separate measure-reference files contain individual definitions, not one executable query.

The [recorded September 16 run](../data/processed/powerbi_analytical_validation.json) passed all **12 baseline scenarios and 81 analytical checks after refreshing the translated hour dimension**. Desktop subsequently saved the refreshed cache. Counts match exactly; recorded total amounts use a $0.01 tolerance. Coverage includes:

- All 2024: **39,677,878 trips**, **$1,135,817,146.18**, **8,784 hours**.
- Positive recorded fee: **3,163,100 trips**; airport pickup: **3,130,315 trips**.
- Newark: **1,238 trips** across the full **8,784 hours**.
- March 10: **23 hours**; November 3: **25 hours**.
- Unknown precipitation: **82 hours** and **313,245 trips**.
- Monthly, borough and combined filters; weighted means; standardized monthly rates; time-window boundaries and zone shares.

## Visual and interaction status

All four pages of the September 16 12:17 English Desktop PDF passed visual review. Charts are populated and English labels fit. The export retains Desktop regional numeric formatting (decimal comma and period thousands separator). Static [report checks](../data/processed/powerbi_report_file_validation.json) covered 80 direct field references, calendar references, page bounds and interaction targets. These are recorded checks of the working report, not evidence that a new machine has completed setup.

**Overview slicer filtering and reset are confirmed.** A reviewed owner screenshot shows Queens plus August and 314,917 trips; the owner confirmed that clearing both filters restored 39,677,878. See [interaction evidence](../data/processed/powerbi_interaction_validation.json). Chart selections and geographic-page interactions were not manually tested. The following checks can be repeated in Desktop:

1. On Overview, select **Month = 8** and **Borough = Queens**: expect **314,917 trips**. Clear both: expect **39,677,878**.
2. Select a chart data point on Overview, confirm other visuals respond, then clear the selection and confirm the original totals return.
3. On the geographic page, confirm slicers update the comparisons while the annual-reference notes stay fixed. Chart selections should preserve the other independent comparisons.

The interaction record distinguishes screenshot evidence, owner confirmation and scenarios not manually tested. Numerical and PDF validation remain separate evidence.
