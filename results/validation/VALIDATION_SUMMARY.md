# Cross-implementation and sensitivity summary

## Excel cross-implementation check

- Overall status: PASS
- Python–Excel checks: 16/16 PASS
- Input: the same bundled processed simulation CSV used by Python
- Source inventory: 5 curves, 1,245 rows
- Common comparison: VGS = VDS = 1.0 V
- Recalculated metrics: Ion, Ioff, Ion/Ioff, SS, SS window endpoints, R² and point count

This checks agreement between separately implemented Python and Excel
calculations. It is not an independent dataset, wafer measurement, or
validation of PTM physical accuracy.

## SS sensitivity analysis

- Overall status: PASS
- Cross-grid inventory: 72 cases
- Evaluable: 60 cases
- Structural N/A: 12 incompatible 11-point/span combinations
- HP maximum absolute baseline deviation: 0.80%
- LP maximum absolute baseline deviation: 0.36%
- Maximum paired symmetric HP–LP difference: 1.44%
- Evaluable windows touching the −0.2 V lower edge: 0
- Current-ceiling check: selected intervals unchanged from 0.1% through 10% of Ion

The workbook uses a project-defined numerical PASS rule: every evaluable result
must remain within ±5% of the 21-point baseline. “Similar” uses a separate
project-defined descriptive rule of ≤5% symmetric HP–LP difference across all
evaluable settings. Neither rule is an industry specification or statistical
equivalence test. The analysis concerns the extraction algorithm, not
manufacturing variation or yield.

The three source tables are reproducible with `python ss_sensitivity.py`:

- `all_window_statistics.csv`: 728 contiguous-window records
- `sensitivity_results.csv`: 72 cross-grid records
- `cutoff_sensitivity.csv`: 10 current-ceiling records
