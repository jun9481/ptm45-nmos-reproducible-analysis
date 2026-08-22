# Figures

`python -B ptm_pipeline.py analyze` writes the transfer-characteristic,
metric-comparison, Vth/DIBL, and extraction-sensitivity figures here.

`id_vg_linear.png` and `id_vg_semilog.png` visualize model-nominal conditions
(HP 1.0 V, LP 1.1 V). Use `hp_lp_common_vdd_metrics.png` for the bias-aligned
quantitative comparison at 1.0 V.

`vth_comparison.png` compares the low- and high-VDS constant-current threshold
voltages. `dibl_comparison.png` compares DIBL across the three non-duplicate
bias conditions. `vth_dibl_sensitivity.png` shows how Vth and DIBL change for
the configured normalized-current multipliers.
