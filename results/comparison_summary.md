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

## Threshold voltage and DIBL

Vth uses the configured constant-current criterion with linear interpolation in log10(ID)-VGS space. DIBL is 1000 x (Vth_low - Vth_high) / (VDS_high - VDS_low), in mV/V.

| Model | Basis | VDS low/high (V) | Vth low (V) | Vth high (V) | DIBL (mV/V) |
|---|---|---:|---:|---:|---:|
| HP | common VDD | 0.05/1 | 0.323646 | 0.184796 | 146.158470 |
| LP | common VDD | 0.05/1 | 0.530393 | 0.457564 | 76.662052 |
| LP | model nominal VDD | 0.05/1.1 | 0.530393 | 0.450642 | 75.953722 |

HP has one row because its model-nominal VDD equals the configured common VDD (1 V); the duplicate comparison is intentionally omitted. LP retains separate common-1-V and model-nominal-1.1-V rows.

## Vth-criterion sensitivity

The configured normalized-current multipliers are applied to every Vth/DIBL comparison. The ranges below are descriptive extraction sensitivity, not statistical confidence intervals.

| Model | Basis | Multiplier range | Vth low range (V) | Vth high range (V) | DIBL range (mV/V) |
|---|---|---:|---:|---:|---:|
| HP | common VDD | 0.1-10x | 0.229008-0.438306 | 0.091902-0.292208 | 144.321454-153.787457 |
| LP | common VDD | 0.1-10x | 0.426521-0.675726 | 0.356342-0.580882 | 73.872819-99.835906 |
| LP | model nominal VDD | 0.1-10x | 0.426521-0.675726 | 0.349485-0.573866 | 73.367321-97.009240 |
