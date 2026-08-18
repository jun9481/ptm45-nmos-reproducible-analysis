#!/usr/bin/env python3
"""Recreate the bundled minimum-local-SS sensitivity tables.

The analysis uses the processed common-1.0-V simulation curves already bundled
with this repository. It varies window length, minimum R-squared, minimum
log-current span, and the maximum-current ceiling. These are extraction-setting
checks, not process-variation or statistical-equivalence tests.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ptm_pipeline import PipelineError, interpolate_at, linear_fit


ROOT = Path(__file__).resolve().parent
COMBINED_PATH = ROOT / "data" / "processed" / "ptm45_combined.csv"
METRICS_PATH = ROOT / "results" / "metrics.csv"
OUTPUT_DIR = ROOT / "results" / "validation"

WINDOW_POINTS = (11, 21, 31, 41)
MIN_R_SQUARED = (0.990, 0.995, 0.999)
MIN_CURRENT_SPAN_DECADES = (0.50, 0.75, 1.00)
CUTOFF_FRACTIONS = (0.001, 0.003, 0.01, 0.03, 0.10)
BASELINE_WINDOW = 21
BASELINE_R_SQUARED = 0.995
BASELINE_SPAN_DECADES = 0.75
BASELINE_MAX_ION_FRACTION = 0.01


ALL_WINDOW_COLUMNS = [
    "application_type",
    "window_points",
    "window_start_index",
    "eligible_points",
    "VGS_min_V",
    "VGS_max_V",
    "ID_min_A",
    "ID_max_A",
    "current_span_decades",
    "slope_decades_per_V",
    "intercept_log10_A",
    "R_squared",
    "SS_mV_dec",
    "touches_lower_sweep_edge",
    "max_ion_fraction",
    "Ion_A",
]

SENSITIVITY_COLUMNS = [
    "application_type",
    "window_points",
    "min_R_squared",
    "min_current_span_decades",
    "max_ion_fraction",
    "status",
    "candidate_count",
    "SS_mV_dec",
    "baseline_SS_mV_dec",
    "deviation_from_baseline_pct",
    "slope_decades_per_V",
    "intercept_log10_A",
    "R_squared",
    "current_span_decades",
    "VGS_min_V",
    "VGS_max_V",
    "ID_min_A",
    "ID_max_A",
    "window_start_index",
    "eligible_points",
    "touches_lower_sweep_edge",
    "Ion_A",
    "selection_rule",
]

CUTOFF_COLUMNS = [
    "application_type",
    "max_ion_fraction",
    "window_points",
    "min_R_squared",
    "min_current_span_decades",
    "status",
    "candidate_count",
    "SS_mV_dec",
    "VGS_min_V",
    "VGS_max_V",
    "touches_lower_sweep_edge",
    "deviation_from_baseline_pct",
]


def common_curve(combined: pd.DataFrame, application_type: str) -> pd.DataFrame:
    """Return the HP or LP curve used for the common-1.0-V comparison."""

    label = "nominal_vdd" if application_type == "HP" else "common_1v"
    frame = combined[
        (combined["application_type"] == application_type)
        & (combined["bias_label"] == label)
        & np.isclose(combined["VDS_V"], 1.0, rtol=0.0, atol=1e-12)
    ].sort_values("VGS_V")
    if frame.empty:
        raise PipelineError(f"Missing common-1.0-V curve for {application_type}.")
    if frame["VGS_V"].duplicated().any():
        raise PipelineError(f"Duplicate VGS samples in common curve for {application_type}.")
    return frame


def enumerate_windows(
    frame: pd.DataFrame,
    application_type: str,
    ion_a: float,
    max_ion_fraction: float,
    window_points: Iterable[int] = WINDOW_POINTS,
) -> pd.DataFrame:
    """Calculate regression statistics for every contiguous eligible window."""

    clean = frame.loc[frame["ID_A"] > 0, ["VGS_V", "ID_A"]].sort_values("VGS_V")
    eligible = clean[clean["ID_A"] <= ion_a * max_ion_fraction]
    full_lower_edge = float(clean["VGS_V"].min())
    evgs = eligible["VGS_V"].to_numpy(dtype=float)
    eid = eligible["ID_A"].to_numpy(dtype=float)
    elog = np.log10(eid)
    rows: list[dict[str, Any]] = []

    for window in window_points:
        if window <= 1:
            raise PipelineError("SS window length must be at least two points.")
        for start in range(0, len(eligible) - window + 1):
            stop = start + window
            x = evgs[start:stop]
            y = elog[start:stop]
            ids = eid[start:stop]
            slope, intercept, r_squared = linear_fit(x, y)
            rows.append(
                {
                    "application_type": application_type,
                    "window_points": window,
                    "window_start_index": start,
                    "eligible_points": len(eligible),
                    "VGS_min_V": float(x.min()),
                    "VGS_max_V": float(x.max()),
                    "ID_min_A": float(ids.min()),
                    "ID_max_A": float(ids.max()),
                    "current_span_decades": float(y.max() - y.min()),
                    "slope_decades_per_V": slope,
                    "intercept_log10_A": intercept,
                    "R_squared": r_squared,
                    "SS_mV_dec": 1000.0 / slope if slope > 0 else math.nan,
                    "touches_lower_sweep_edge": math.isclose(
                        float(x.min()), full_lower_edge, rel_tol=0.0, abs_tol=1e-12
                    ),
                    "max_ion_fraction": max_ion_fraction,
                    "Ion_A": ion_a,
                }
            )
    return pd.DataFrame(rows, columns=ALL_WINDOW_COLUMNS)


def select_best(
    windows: pd.DataFrame, min_r_squared: float, min_span_decades: float
) -> tuple[pd.Series | None, int]:
    eligible = windows[
        (windows["slope_decades_per_V"] > 0)
        & (windows["R_squared"] >= min_r_squared)
        & (windows["current_span_decades"] >= min_span_decades)
    ]
    if eligible.empty:
        return None, 0
    ordered = eligible.sort_values(
        ["slope_decades_per_V", "R_squared"], ascending=[False, False]
    )
    return ordered.iloc[0], len(eligible)


def baseline_metrics(metrics: pd.DataFrame) -> dict[str, dict[str, float]]:
    common = metrics[metrics["comparison_basis"] == "common_vdd"]
    result: dict[str, dict[str, float]] = {}
    for application_type in ("HP", "LP"):
        row = common[common["application_type"] == application_type]
        if len(row) != 1:
            raise PipelineError(
                f"Expected one common-VDD metrics row for {application_type}; got {len(row)}."
            )
        result[application_type] = {
            "Ion_A": float(row.iloc[0]["Ion_A"]),
            "SS_mV_dec": float(row.iloc[0]["SS_mV_dec"]),
        }
    return result


def sensitivity_row(
    application_type: str,
    window: int,
    min_r_squared: float,
    min_span: float,
    baseline: dict[str, float],
    best: pd.Series | None,
    candidate_count: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "application_type": application_type,
        "window_points": window,
        "min_R_squared": min_r_squared,
        "min_current_span_decades": min_span,
        "max_ion_fraction": BASELINE_MAX_ION_FRACTION,
        "status": "VALID" if best is not None else "N/A",
        "candidate_count": candidate_count,
        "SS_mV_dec": math.nan,
        "baseline_SS_mV_dec": baseline["SS_mV_dec"],
        "deviation_from_baseline_pct": math.nan,
        "slope_decades_per_V": math.nan,
        "intercept_log10_A": math.nan,
        "R_squared": math.nan,
        "current_span_decades": math.nan,
        "VGS_min_V": math.nan,
        "VGS_max_V": math.nan,
        "ID_min_A": math.nan,
        "ID_max_A": math.nan,
        "window_start_index": math.nan,
        "eligible_points": math.nan,
        "touches_lower_sweep_edge": math.nan,
        "Ion_A": baseline["Ion_A"],
        "selection_rule": "maximum positive slope; R_squared tie-breaker",
    }
    if best is None:
        return row

    ss = float(best["SS_mV_dec"])
    row.update(
        {
            "SS_mV_dec": ss,
            "deviation_from_baseline_pct": abs(ss - baseline["SS_mV_dec"])
            / baseline["SS_mV_dec"]
            * 100.0,
            "slope_decades_per_V": float(best["slope_decades_per_V"]),
            "intercept_log10_A": float(best["intercept_log10_A"]),
            "R_squared": float(best["R_squared"]),
            "current_span_decades": float(best["current_span_decades"]),
            "VGS_min_V": float(best["VGS_min_V"]),
            "VGS_max_V": float(best["VGS_max_V"]),
            "ID_min_A": float(best["ID_min_A"]),
            "ID_max_A": float(best["ID_max_A"]),
            "window_start_index": int(best["window_start_index"]),
            "eligible_points": int(best["eligible_points"]),
            "touches_lower_sweep_edge": bool(best["touches_lower_sweep_edge"]),
        }
    )
    return row


def generate_tables(
    combined: pd.DataFrame, metrics: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return all-window, cross-grid, and current-ceiling tables."""

    baselines = baseline_metrics(metrics)
    all_window_frames: list[pd.DataFrame] = []
    sensitivity_rows: list[dict[str, Any]] = []
    cutoff_rows: list[dict[str, Any]] = []

    for application_type in ("HP", "LP"):
        frame = common_curve(combined, application_type)
        baseline = baselines[application_type]
        ion_from_curve = interpolate_at(frame, 1.0)
        if not math.isclose(
            ion_from_curve, baseline["Ion_A"], rel_tol=1e-11, abs_tol=0.0
        ):
            raise PipelineError(
                f"Bundled Ion does not match the common curve for {application_type}."
            )

        windows = enumerate_windows(
            frame,
            application_type,
            baseline["Ion_A"],
            BASELINE_MAX_ION_FRACTION,
        )
        all_window_frames.append(windows)
        for window in WINDOW_POINTS:
            window_rows = windows[windows["window_points"] == window]
            for min_r_squared in MIN_R_SQUARED:
                for min_span in MIN_CURRENT_SPAN_DECADES:
                    best, candidate_count = select_best(
                        window_rows, min_r_squared, min_span
                    )
                    sensitivity_rows.append(
                        sensitivity_row(
                            application_type,
                            window,
                            min_r_squared,
                            min_span,
                            baseline,
                            best,
                            candidate_count,
                        )
                    )

        for max_fraction in CUTOFF_FRACTIONS:
            cutoff_windows = enumerate_windows(
                frame,
                application_type,
                baseline["Ion_A"],
                max_fraction,
                (BASELINE_WINDOW,),
            )
            best, candidate_count = select_best(
                cutoff_windows, BASELINE_R_SQUARED, BASELINE_SPAN_DECADES
            )
            if best is None:
                cutoff_rows.append(
                    {
                        "application_type": application_type,
                        "max_ion_fraction": max_fraction,
                        "window_points": BASELINE_WINDOW,
                        "min_R_squared": BASELINE_R_SQUARED,
                        "min_current_span_decades": BASELINE_SPAN_DECADES,
                        "status": "N/A",
                        "candidate_count": 0,
                        "SS_mV_dec": math.nan,
                        "VGS_min_V": math.nan,
                        "VGS_max_V": math.nan,
                        "touches_lower_sweep_edge": math.nan,
                        "deviation_from_baseline_pct": math.nan,
                    }
                )
                continue
            ss = float(best["SS_mV_dec"])
            cutoff_rows.append(
                {
                    "application_type": application_type,
                    "max_ion_fraction": max_fraction,
                    "window_points": BASELINE_WINDOW,
                    "min_R_squared": BASELINE_R_SQUARED,
                    "min_current_span_decades": BASELINE_SPAN_DECADES,
                    "status": "VALID",
                    "candidate_count": candidate_count,
                    "SS_mV_dec": ss,
                    "VGS_min_V": float(best["VGS_min_V"]),
                    "VGS_max_V": float(best["VGS_max_V"]),
                    "touches_lower_sweep_edge": bool(
                        best["touches_lower_sweep_edge"]
                    ),
                    "deviation_from_baseline_pct": abs(
                        ss - baseline["SS_mV_dec"]
                    )
                    / baseline["SS_mV_dec"]
                    * 100.0,
                }
            )

    all_windows = pd.concat(all_window_frames, ignore_index=True)[ALL_WINDOW_COLUMNS]
    sensitivity = pd.DataFrame(sensitivity_rows, columns=SENSITIVITY_COLUMNS)
    cutoff = pd.DataFrame(cutoff_rows, columns=CUTOFF_COLUMNS)
    return all_windows, sensitivity, cutoff


def summarize(sensitivity: pd.DataFrame) -> dict[str, float | int]:
    valid = sensitivity[sensitivity["status"] == "VALID"]
    paired = valid.pivot_table(
        index=["window_points", "min_R_squared", "min_current_span_decades"],
        columns="application_type",
        values="SS_mV_dec",
        aggfunc="first",
    ).dropna(subset=["HP", "LP"])
    symmetric_difference = (
        (paired["HP"] - paired["LP"]).abs()
        / ((paired["HP"] + paired["LP"]) / 2.0)
        * 100.0
    )
    return {
        "total": len(sensitivity),
        "valid": len(valid),
        "not_applicable": int((sensitivity["status"] == "N/A").sum()),
        "edge_contacts": int(
            valid["touches_lower_sweep_edge"].eq(True).sum()
        ),
        "max_paired_symmetric_difference_pct": float(symmetric_difference.max()),
    }


def write_tables(
    all_windows: pd.DataFrame,
    sensitivity: pd.DataFrame,
    cutoff: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    options = {"index": False, "float_format": "%.15g", "lineterminator": "\n"}
    all_windows.to_csv(output_dir / "all_window_statistics.csv", **options)
    sensitivity.to_csv(output_dir / "sensitivity_results.csv", **options)
    cutoff.to_csv(output_dir / "cutoff_sensitivity.csv", **options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined", type=Path, default=COMBINED_PATH)
    parser.add_argument("--metrics", type=Path, default=METRICS_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    # Ordinary pandas parsing matches the precision used to construct the
    # workbook's cached sensitivity values.
    combined = pd.read_csv(args.combined)
    metrics = pd.read_csv(args.metrics)
    all_windows, sensitivity, cutoff = generate_tables(combined, metrics)
    write_tables(all_windows, sensitivity, cutoff, args.output_dir)
    summary = summarize(sensitivity)
    print(
        "Wrote 728 windows, "
        f"{summary['valid']}/{summary['total']} evaluable grid rows, and "
        f"{len(cutoff)} cutoff checks; lower-edge contacts="
        f"{summary['edge_contacts']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
