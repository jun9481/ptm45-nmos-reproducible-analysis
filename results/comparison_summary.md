# Metric extraction summary

Ion and Ioff are extracted at the exact endpoint definitions shown in `metrics.csv`. SS is the minimum sliding-window linear-regression value in log10(ID)-VGS space; the selected range, point count, and R-squared are stored alongside the result.

## Model-nominal conditions

The HP and LP nominal results use different supply voltages (1.0 V and 1.1 V). They describe each model at its intended nominal condition, but their Ion difference is not attributable to model type alone.

| Model | VDS (V) | Ion (uA/um) | Ioff (A/um) | Ion/Ioff | Minimum local SS (mV/dec) | Local-fit R2 |
|---|---:|---:|---:|---:|---:|---:|
| HP | 1 | 1339 | 2.0045e-08 | 6.6810e+04 | 87.506 | 0.999999 |
| LP | 1.1 | 524.9 | 2.5257e-11 | 2.0784e+07 | 86.674 | 0.999994 |

## Common-voltage comparison (1 V)

This section holds VGS and VDS constant, so it is the primary bias-aligned descriptive HP-LP model comparison.

| Model | VDS (V) | Ion (uA/um) | Ioff (A/um) | Ion/Ioff | Minimum local SS (mV/dec) | Local-fit R2 |
|---|---:|---:|---:|---:|---:|---:|
| HP | 1 | 1339 | 2.0045e-08 | 6.6810e+04 | 87.506 | 0.999999 |
| LP | 1 | 402 | 2.1150e-11 | 1.9006e+07 | 86.648 | 0.999994 |

## Interpretation

- HP Ion is 3.331x LP at the tested DC bias. Capacitance and circuit delay were not evaluated.
- HP Ioff is 947.74x LP; LP therefore has lower static leakage under this condition.
- LP Ion/Ioff is 284.48x HP; this DC ratio is not a measurement of total power.
- The minimum-local-SS gap is 0.858 mV/dec. Under this project's descriptive <=5% criterion, the bundled sensitivity analysis supports treating the values as similar across the tested extraction settings. This is not a statistical equivalence test.

These are nominal PTM simulation results, not measured-wafer or process-yield results.
