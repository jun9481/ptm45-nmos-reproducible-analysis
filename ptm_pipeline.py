#!/usr/bin/env python3
"""Reproducible PTM 45 nm NMOS transfer-characteristic pipeline.

The script deliberately does not redistribute PTM model cards. Download the HP
and LP cards from the official PTM host, place them under ``models/``, and run:

    python ptm_pipeline.py all

The pipeline validates model metadata, generates ngspice netlists, runs DC
sweeps, preserves raw output, creates tidy CSV files, extracts Ion/Ioff/SS, and
generates plots and a synthetic validation data set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ptm45-matplotlib-cache")
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CONFIG_PATH = ROOT / "project_config.json"
IOFF_DEFINITION_VGS_V = 0.0
METRICS_COLUMNS = [
    "application_type",
    "bias_label",
    "comparison_basis",
    "VDS_V",
    "Ion_definition_VGS_V",
    "Ioff_definition_VGS_V",
    "nominal_VDD_V",
    "Ion_A",
    "Ioff_A",
    "Ion_Ioff_ratio",
    "log10_Ion_Ioff",
    "SS_mV_dec",
    "SS_fit_VGS_min_V",
    "SS_fit_VGS_max_V",
    "SS_fit_ID_min_A",
    "SS_fit_ID_max_A",
    "SS_fit_R_squared",
    "SS_fit_points",
    "SS_method",
    "Ion_A_per_um",
    "Ioff_A_per_um",
]
METRICS_FLOAT_FORMAT = "%.12g"


class PipelineError(RuntimeError):
    """A user-actionable pipeline failure."""


@dataclass(frozen=True)
class ModelInfo:
    application_type: str
    path: Path
    model_name: str
    nominal_vdd_v: float
    sha256: str
    official_download_url: str


@dataclass(frozen=True)
class SweepSpec:
    application_type: str
    bias_label: str
    comparison_basis: str
    vds_v: float
    vgs_start_v: float
    vgs_stop_v: float
    nominal_vdd_v: float
    model: ModelInfo

    @property
    def stem(self) -> str:
        vds = format_voltage_for_name(self.vds_v)
        return f"ptm45_{self.application_type.lower()}_vds_{vds}"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_voltage_for_name(value: float) -> str:
    return f"{value:g}".replace(".", "p") + "v"


def spice_number(value: float) -> str:
    return f"{value:.12g}"


def parse_model_metadata(text: str) -> tuple[str, float]:
    model_match = re.search(
        r"^\s*\.model\s+(\S+)\s+nmos\b", text, flags=re.IGNORECASE | re.MULTILINE
    )
    vdd_match = re.search(
        r"nominal\s+Vdd\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*V",
        text,
        flags=re.IGNORECASE,
    )
    if not model_match:
        raise PipelineError("NMOS .model declaration was not found in the model card.")
    if not vdd_match:
        raise PipelineError(
            "A 'nominal Vdd = ...V' comment was not found in the model card. "
            "Confirm that this is the official PTM 45 nm file."
        )
    return model_match.group(1), float(vdd_match.group(1))


def validate_models(
    config: dict[str, Any], root: Path = ROOT
) -> dict[str, ModelInfo]:
    infos: dict[str, ModelInfo] = {}
    failures: list[str] = []

    for application_type, entry in config["models"].items():
        path = root / entry["path"]
        if not path.is_file():
            failures.append(
                f"- {application_type}: missing {path.relative_to(root)}\n"
                f"  Official download: {entry['official_download_url']}"
            )
            continue

        expected_sha = str(entry.get("expected_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            failures.append(
                f"- {application_type}: expected_sha256 must be 64 lowercase "
                "hexadecimal characters in project_config.json."
            )
            continue

        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            failures.append(
                f"- {application_type}: model-card SHA-256 mismatch.\n"
                f"  Expected: {expected_sha}\n"
                f"  Actual:   {actual_sha}\n"
                f"  Download the intended file again: {entry['official_download_url']}"
            )
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            model_name, nominal_vdd_v = parse_model_metadata(text)
        except PipelineError as exc:
            failures.append(f"- {application_type}: {exc}")
            continue

        expected_name = str(entry["expected_model_name"])
        expected_vdd = float(entry["expected_nominal_vdd_v"])
        if model_name.lower() != expected_name.lower():
            failures.append(
                f"- {application_type}: NMOS model name is '{model_name}', "
                f"expected '{expected_name}'. Update project_config.json only after inspection."
            )
            continue
        if not math.isclose(nominal_vdd_v, expected_vdd, abs_tol=1e-9):
            failures.append(
                f"- {application_type}: model comment reports VDD={nominal_vdd_v:g} V, "
                f"expected {expected_vdd:g} V. Do not simulate until the file is verified."
            )
            continue

        infos[application_type] = ModelInfo(
            application_type=application_type,
            path=path,
            model_name=model_name,
            nominal_vdd_v=nominal_vdd_v,
            sha256=actual_sha,
            official_download_url=entry["official_download_url"],
        )

    if failures:
        raise PipelineError("Model-card validation failed:\n" + "\n".join(failures))
    return infos


def build_sweep_specs(
    config: dict[str, Any], models: dict[str, ModelInfo]
) -> list[SweepSpec]:
    project = config["project"]
    low_vds_v = float(project["low_vds_v"])
    vgs_start_v = float(project["vgs_start_v"])
    vgs_step_v = float(project["vgs_step_v"])
    if not math.isfinite(vgs_start_v):
        raise PipelineError("vgs_start_v must be finite.")
    if not math.isfinite(vgs_step_v) or vgs_step_v <= 0:
        raise PipelineError("vgs_step_v must be positive and finite.")
    if vgs_start_v > IOFF_DEFINITION_VGS_V:
        raise PipelineError("The VGS sweep must include 0 V for the Ioff definition.")
    zero_intervals = (IOFF_DEFINITION_VGS_V - vgs_start_v) / vgs_step_v
    if not math.isclose(zero_intervals, round(zero_intervals), abs_tol=1e-9):
        raise PipelineError("The configured VGS grid must contain an exact 0 V sample.")
    specs: list[SweepSpec] = []

    for application_type in ("HP", "LP"):
        model = models[application_type]
        specs.extend(
            [
                SweepSpec(
                    application_type=application_type,
                    bias_label="low_vds",
                    comparison_basis="low_drain_bias",
                    vds_v=low_vds_v,
                    vgs_start_v=vgs_start_v,
                    vgs_stop_v=model.nominal_vdd_v,
                    nominal_vdd_v=model.nominal_vdd_v,
                    model=model,
                ),
                SweepSpec(
                    application_type=application_type,
                    bias_label="nominal_vdd",
                    comparison_basis="model_nominal_vdd",
                    vds_v=model.nominal_vdd_v,
                    vgs_start_v=vgs_start_v,
                    vgs_stop_v=model.nominal_vdd_v,
                    nominal_vdd_v=model.nominal_vdd_v,
                    model=model,
                ),
            ]
        )

    if bool(project.get("include_common_vdd_curve", False)):
        common_vdd = float(project["common_vdd_v"])
        for application_type in ("HP", "LP"):
            model = models[application_type]
            duplicate = any(
                spec.application_type == application_type
                and math.isclose(spec.vds_v, common_vdd, abs_tol=1e-12)
                and math.isclose(spec.vgs_stop_v, common_vdd, abs_tol=1e-12)
                for spec in specs
            )
            if not duplicate:
                specs.append(
                    SweepSpec(
                        application_type=application_type,
                        bias_label=f"common_{format_voltage_for_name(common_vdd)}",
                        comparison_basis="common_vdd",
                        vds_v=common_vdd,
                        vgs_start_v=vgs_start_v,
                        vgs_stop_v=common_vdd,
                        nominal_vdd_v=model.nominal_vdd_v,
                        model=model,
                    )
                )
    return specs


def render_netlist(spec: SweepSpec, config: dict[str, Any], raw_path: Path) -> str:
    project = config["project"]
    width_um = float(project["width_um"])
    length_um = float(project["length_um"])
    temperature_c = float(project["temperature_c"])
    vgs_step_v = float(project["vgs_step_v"])

    # ngspice runs with cwd=ROOT, so a repository-relative include is portable
    # and does not expose a contributor's local absolute path.
    try:
        model_path = spec.model.path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise PipelineError("Model path must be inside the project directory.") from exc
    try:
        output_path = raw_path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise PipelineError("Raw output path must be inside the project directory.") from exc

    return f"""* PTM 45 nm {spec.application_type} NMOS ID-VG transfer curve
* Generated by ptm_pipeline.py; do not edit generated files by hand.
* VDS={spec.vds_v:g} V, VGS={spec.vgs_start_v:g}..{spec.vgs_stop_v:g} V, step={vgs_step_v:g} V

.include \"{model_path}\"
.temp {spice_number(temperature_c)}

VGS gate 0 0
VDS drain 0 {spice_number(spec.vds_v)}
M1 drain gate 0 0 {spec.model.model_name} W={spice_number(width_um)}u L={spice_number(length_um)}u

.control
set noaskquit
set wr_vecnames
set wr_singlescale
option numdgt=15
dc VGS {spice_number(spec.vgs_start_v)} {spice_number(spec.vgs_stop_v)} {spice_number(vgs_step_v)}
* I(VDS) uses the voltage-source reference direction. The source supplies the
* NMOS drain, so physical positive drain current is -I(VDS), not abs(I(VDS)).
let ID_A = -i(VDS)
* Keep the wrdata filename relative and unquoted. On Windows, ngspice may pass
* quotes through to fopen(), which makes an otherwise valid C:/... path invalid.
wrdata {output_path} ID_A
quit
.endc

.end
"""


def generate_netlists(
    config: dict[str, Any], models: dict[str, ModelInfo]
) -> list[SweepSpec]:
    specs = build_sweep_specs(config, models)
    netlist_dir = ROOT / "netlists" / "generated"
    raw_dir = ROOT / "data" / "raw"
    netlist_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        netlist_path = netlist_dir / f"{spec.stem}.cir"
        raw_path = raw_dir / f"{spec.stem}_raw.txt"
        netlist_path.write_text(
            render_netlist(spec, config, raw_path), encoding="utf-8", newline="\n"
        )
    return specs


def find_ngspice(explicit: str | None = None) -> str:
    candidate = explicit or shutil.which("ngspice")
    if not candidate:
        raise PipelineError(
            "ngspice was not found on PATH. Install ngspice, open a new terminal, "
            "and confirm with 'ngspice --version'. You may also pass --ngspice PATH."
        )
    return candidate


def run_ngspice(specs: Iterable[SweepSpec], ngspice: str) -> None:
    logs_dir = ROOT / "results" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        netlist_path = ROOT / "netlists" / "generated" / f"{spec.stem}.cir"
        raw_path = ROOT / "data" / "raw" / f"{spec.stem}_raw.txt"
        log_path = logs_dir / f"{spec.stem}.log"
        if raw_path.exists():
            raw_path.unlink()

        completed = subprocess.run(
            [ngspice, "-b", str(netlist_path)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        log_path.write_text(
            stdout + "\n--- STDERR ---\n" + stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0 or not raw_path.is_file():
            raise PipelineError(
                f"ngspice failed for {spec.stem}. Inspect {log_path.relative_to(ROOT)}."
            )
        if raw_path.stat().st_size == 0:
            raise PipelineError(f"ngspice created an empty file: {raw_path}")


FLOAT_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
)


def parse_wrdata(path: Path) -> pd.DataFrame:
    """Parse a two-column ngspice wrdata table without trusting its header."""

    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = FLOAT_RE.findall(line)
        if len(tokens) < 2:
            continue
        try:
            values = [float(token.replace("D", "E").replace("d", "e")) for token in tokens]
        except ValueError:
            continue
        # With wr_singlescale and one real output vector the columns are VGS, ID.
        rows.append((values[0], values[1]))

    if len(rows) < 3:
        raise PipelineError(
            f"Could not parse at least three numeric rows from {path.relative_to(ROOT)}."
        )

    frame = pd.DataFrame(rows, columns=["VGS_V", "ID_A"])
    if frame["VGS_V"].duplicated().any():
        raise PipelineError(f"Duplicate VGS values found in {path.relative_to(ROOT)}.")
    if not np.all(np.diff(frame["VGS_V"].to_numpy()) > 0):
        raise PipelineError(f"VGS is not strictly increasing in {path.relative_to(ROOT)}.")
    if not np.isfinite(frame[["VGS_V", "ID_A"]].to_numpy()).all():
        raise PipelineError(f"Non-finite values found in {path.relative_to(ROOT)}.")
    if (frame["ID_A"] <= 0).mean() > 0.05:
        raise PipelineError(
            f"More than 5% of ID values are non-positive in {path.relative_to(ROOT)}. "
            "Inspect voltage-source current direction and the ngspice log."
        )
    return frame


def expected_row_count(vgs_start_v: float, vgs_stop_v: float, step_v: float) -> int:
    if not math.isfinite(step_v) or step_v <= 0:
        raise PipelineError("VGS step must be positive and finite.")
    if vgs_stop_v < vgs_start_v:
        raise PipelineError("VGS stop must be greater than or equal to VGS start.")
    intervals = (vgs_stop_v - vgs_start_v) / step_v
    rounded = round(intervals)
    if not math.isclose(intervals, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise PipelineError("VGS range must be an integer multiple of the configured step.")
    return int(rounded) + 1


def process_raw_data(
    config: dict[str, Any], specs: Iterable[SweepSpec]
) -> pd.DataFrame:
    project = config["project"]
    step_v = float(project["vgs_step_v"])
    processed_dir = ROOT / "data" / "processed"
    metadata_dir = ROOT / "data" / "metadata"
    processed_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    all_frames: list[pd.DataFrame] = []
    manifest_rows: list[dict[str, Any]] = []

    for spec in specs:
        raw_path = ROOT / "data" / "raw" / f"{spec.stem}_raw.txt"
        if not raw_path.is_file():
            raise PipelineError(
                f"Missing raw file {raw_path.relative_to(ROOT)}. Run 'simulate' first."
            )
        frame = parse_wrdata(raw_path)
        expected = expected_row_count(spec.vgs_start_v, spec.vgs_stop_v, step_v)
        if len(frame) != expected:
            raise PipelineError(
                f"Unexpected row count in {raw_path.name}: got {len(frame)}, expected {expected}."
            )
        if not math.isclose(
            float(frame["VGS_V"].iloc[0]), spec.vgs_start_v, abs_tol=step_v / 10
        ):
            raise PipelineError(
                f"First VGS does not match the requested start in {raw_path.name}."
            )
        if not math.isclose(
            float(frame["VGS_V"].iloc[-1]), spec.vgs_stop_v, abs_tol=step_v / 10
        ):
            raise PipelineError(f"Last VGS does not match the requested stop in {raw_path.name}.")
        spacing = np.diff(frame["VGS_V"].to_numpy(dtype=float))
        if not np.allclose(
            spacing, step_v, rtol=0.0, atol=max(1e-12, step_v * 1e-6)
        ):
            raise PipelineError(f"VGS grid spacing is inconsistent in {raw_path.name}.")

        frame.insert(0, "model_family", "PTM")
        frame.insert(1, "device_type", project["device_type"])
        frame.insert(2, "technology_nm", int(project["technology_nm"]))
        frame.insert(3, "application_type", spec.application_type)
        frame.insert(4, "W_um", float(project["width_um"]))
        frame.insert(5, "L_um", float(project["length_um"]))
        frame.insert(6, "temperature_C", float(project["temperature_c"]))
        frame.insert(7, "VDS_V", spec.vds_v)
        # VGS_V and ID_A are already in the desired order after inserted metadata.
        frame["bias_label"] = spec.bias_label
        frame["comparison_basis"] = spec.comparison_basis
        frame["nominal_VDD_V"] = spec.nominal_vdd_v
        frame["source_type"] = "simulation"
        frame["simulator"] = "ngspice"
        frame["model_file_sha256"] = spec.model.sha256
        frame["raw_file"] = raw_path.relative_to(ROOT).as_posix()
        all_frames.append(frame)

        manifest_rows.append(
            {
                "application_type": spec.application_type,
                "bias_label": spec.bias_label,
                "comparison_basis": spec.comparison_basis,
                "model_file": spec.model.path.relative_to(ROOT).as_posix(),
                "model_file_sha256": spec.model.sha256,
                "model_name": spec.model.model_name,
                "nominal_VDD_V": spec.nominal_vdd_v,
                "VDS_V": spec.vds_v,
                "VGS_start_V": spec.vgs_start_v,
                "VGS_stop_V": spec.vgs_stop_v,
                "VGS_step_V": step_v,
                "row_count": len(frame),
                "raw_file": raw_path.relative_to(ROOT).as_posix(),
                "raw_file_sha256": sha256_file(raw_path),
            }
        )

    combined = pd.concat(all_frames, ignore_index=True)
    ordered = [
        "model_family",
        "device_type",
        "technology_nm",
        "application_type",
        "W_um",
        "L_um",
        "temperature_C",
        "VDS_V",
        "VGS_V",
        "ID_A",
        "bias_label",
        "comparison_basis",
        "nominal_VDD_V",
        "source_type",
        "simulator",
        "model_file_sha256",
        "raw_file",
    ]
    combined = combined[ordered]

    combined.to_csv(processed_dir / "ptm45_combined.csv", index=False)
    for application_type in ("HP", "LP"):
        subset = combined[combined["application_type"] == application_type]
        subset.to_csv(
            processed_dir / f"ptm45_{application_type.lower()}_nmos_transfer.csv",
            index=False,
        )
    pd.DataFrame(manifest_rows).to_csv(metadata_dir / "data_manifest.csv", index=False)
    write_simulation_conditions(config, specs)
    return combined


def write_simulation_conditions(
    config: dict[str, Any], specs: Iterable[SweepSpec]
) -> None:
    project = config["project"]
    lines = [
        "# Simulation conditions",
        "",
        "- Model source: Predictive Technology Model, University of Minnesota",
        "- PTM landing page: https://mec.umn.edu/ptm",
        "- Data type: PTM model-based simulation; not measured silicon data",
        "- Simulator: ngspice",
        f"- Device: {project['device_type']}",
        f"- W: {float(project['width_um']):g} um",
        f"- L: {float(project['length_um']):g} um ({float(project['length_um']) * 1000:g} nm)",
        "- Body condition: VB = VS = 0 V",
        f"- Temperature: {float(project['temperature_c']):g} degC",
        f"- VGS start: {float(project['vgs_start_v']):g} V",
        f"- VGS step: {float(project['vgs_step_v']):g} V",
        "",
        "## Sweep inventory",
        "",
        "| Application | Bias label | VDS (V) | VGS range (V) | Comparison basis |",
        "|---|---:|---:|---:|---|",
    ]
    for spec in specs:
        lines.append(
            f"| {spec.application_type} | {spec.bias_label} | {spec.vds_v:g} | "
            f"{spec.vgs_start_v:g} to {spec.vgs_stop_v:g} | {spec.comparison_basis} |"
        )
    lines.extend(
        [
            "",
            "## Model-card identities",
            "",
        ]
    )
    seen: set[str] = set()
    for spec in specs:
        if spec.application_type in seen:
            continue
        seen.add(spec.application_type)
        lines.extend(
            [
                f"### {spec.application_type}",
                "",
                f"- File: `{spec.model.path.relative_to(ROOT).as_posix()}`",
                f"- NMOS model name: `{spec.model.model_name}`",
                f"- Nominal VDD: {spec.model.nominal_vdd_v:g} V",
                f"- SHA-256: `{spec.model.sha256}`",
                f"- Official download: {spec.model.official_download_url}",
                "",
            ]
        )
    lines.append(
        f"Generated at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    path = ROOT / "data" / "metadata" / "simulation_conditions.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def interpolate_at(frame: pd.DataFrame, vgs_v: float) -> float:
    x = frame["VGS_V"].to_numpy(dtype=float)
    y = frame["ID_A"].to_numpy(dtype=float)
    if vgs_v < x.min() - 1e-12 or vgs_v > x.max() + 1e-12:
        raise PipelineError(f"Requested VGS={vgs_v:g} V lies outside the simulated range.")
    nearest = int(np.argmin(np.abs(x - vgs_v)))
    if math.isclose(float(x[nearest]), vgs_v, rel_tol=0.0, abs_tol=1e-9):
        return float(y[nearest])
    return float(np.interp(vgs_v, x, y))


def linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residual = float(np.sum((y - predicted) ** 2))
    total = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - residual / total if total > 0 else 1.0
    return float(slope), float(intercept), r_squared


def extract_ss(
    frame: pd.DataFrame,
    ion_a: float,
    settings: dict[str, Any],
    curve_key: str,
) -> dict[str, float | int | str]:
    clean = frame.loc[frame["ID_A"] > 0, ["VGS_V", "ID_A"]].sort_values("VGS_V")
    if len(clean) < 5:
        raise PipelineError(f"Not enough positive-current samples for SS: {curve_key}")

    log_id = np.log10(clean["ID_A"].to_numpy(dtype=float))
    vgs = clean["VGS_V"].to_numpy(dtype=float)
    manual_ranges = settings.get("manual_vgs_ranges_v", {})
    if curve_key in manual_ranges:
        lower, upper = map(float, manual_ranges[curve_key])
        mask = (vgs >= lower) & (vgs <= upper)
        if mask.sum() < 5:
            raise PipelineError(f"Manual SS range has fewer than five points: {curve_key}")
        slope, _, r_squared = linear_fit(vgs[mask], log_id[mask])
        if slope <= 0:
            raise PipelineError(f"Manual SS fit has a non-positive slope: {curve_key}")
        return {
            "SS_mV_dec": 1000.0 / slope,
            "SS_fit_VGS_min_V": float(vgs[mask].min()),
            "SS_fit_VGS_max_V": float(vgs[mask].max()),
            "SS_fit_ID_min_A": float(10 ** log_id[mask].min()),
            "SS_fit_ID_max_A": float(10 ** log_id[mask].max()),
            "SS_fit_R_squared": r_squared,
            "SS_fit_points": int(mask.sum()),
            "SS_method": "manual_linear_regression",
        }

    window = int(settings["window_points"])
    min_decades = float(settings["min_current_span_decades"])
    min_r_squared = float(settings["min_r_squared"])
    max_current = ion_a * float(settings["max_ion_fraction"])
    eligible = clean[clean["ID_A"] <= max_current]
    if len(eligible) < window:
        raise PipelineError(
            f"Fewer than {window} points lie below {max_current:.3e} A for SS: {curve_key}. "
            "Adjust ss_extraction settings only after inspecting the semilog plot."
        )

    evgs = eligible["VGS_V"].to_numpy(dtype=float)
    elog = np.log10(eligible["ID_A"].to_numpy(dtype=float))
    candidates: list[dict[str, float | int]] = []
    for start in range(0, len(eligible) - window + 1):
        stop = start + window
        x = evgs[start:stop]
        y = elog[start:stop]
        span = float(y.max() - y.min())
        if span < min_decades:
            continue
        slope, _, r_squared = linear_fit(x, y)
        if slope <= 0 or r_squared < min_r_squared:
            continue
        candidates.append(
            {
                "slope": slope,
                "r_squared": r_squared,
                "start": start,
                "stop": stop,
                "span": span,
            }
        )

    if not candidates:
        raise PipelineError(
            f"No SS window passed R^2 >= {min_r_squared:g} and span >= {min_decades:g} "
            f"decades for {curve_key}. Inspect the curve and set a manual VGS range."
        )

    # Highest d(log10 ID)/dVGS corresponds to minimum subthreshold swing.
    best = max(candidates, key=lambda item: (float(item["slope"]), float(item["r_squared"])))
    start = int(best["start"])
    stop = int(best["stop"])
    return {
        "SS_mV_dec": 1000.0 / float(best["slope"]),
        "SS_fit_VGS_min_V": float(evgs[start:stop].min()),
        "SS_fit_VGS_max_V": float(evgs[start:stop].max()),
        "SS_fit_ID_min_A": float(10 ** elog[start:stop].min()),
        "SS_fit_ID_max_A": float(10 ** elog[start:stop].max()),
        "SS_fit_R_squared": float(best["r_squared"]),
        "SS_fit_points": window,
        "SS_method": "minimum_SS_sliding_linear_regression",
    }


def analyze_curve(
    frame: pd.DataFrame,
    target_vgs_v: float,
    settings: dict[str, Any],
    curve_key: str,
) -> dict[str, Any]:
    ion_a = interpolate_at(frame, target_vgs_v)
    ioff_a = interpolate_at(frame, IOFF_DEFINITION_VGS_V)
    if ion_a <= 0 or ioff_a <= 0:
        raise PipelineError(f"Ion and Ioff must be positive for {curve_key}.")
    metrics: dict[str, Any] = {
        "Ion_A": ion_a,
        "Ioff_A": ioff_a,
        "Ion_Ioff_ratio": ion_a / ioff_a,
        "log10_Ion_Ioff": math.log10(ion_a / ioff_a),
    }
    metrics.update(extract_ss(frame, ion_a, settings, curve_key))
    return metrics


def select_curve(
    combined: pd.DataFrame, application_type: str, bias_label: str
) -> pd.DataFrame:
    frame = combined[
        (combined["application_type"] == application_type)
        & (combined["bias_label"] == bias_label)
    ]
    if frame.empty:
        raise PipelineError(f"Curve not found: {application_type}/{bias_label}")
    return frame.sort_values("VGS_V")


def analyze_data(config: dict[str, Any], combined: pd.DataFrame) -> pd.DataFrame:
    settings = config["ss_extraction"]
    width_um = float(config["project"]["width_um"])
    rows: list[dict[str, Any]] = []

    for application_type in ("HP", "LP"):
        frame = select_curve(combined, application_type, "nominal_vdd")
        nominal_vdd = float(frame["nominal_VDD_V"].iloc[0])
        curve_key = f"{application_type}.nominal_vdd"
        row: dict[str, Any] = {
            "application_type": application_type,
            "bias_label": "nominal_vdd",
            "comparison_basis": "model_nominal_vdd",
            "VDS_V": nominal_vdd,
            "Ion_definition_VGS_V": nominal_vdd,
            "Ioff_definition_VGS_V": IOFF_DEFINITION_VGS_V,
            "nominal_VDD_V": nominal_vdd,
        }
        row.update(analyze_curve(frame, nominal_vdd, settings, curve_key))
        row["Ion_A_per_um"] = row["Ion_A"] / width_um
        row["Ioff_A_per_um"] = row["Ioff_A"] / width_um
        rows.append(row)

    project = config["project"]
    if bool(project.get("include_common_vdd_curve", False)):
        common_vdd = float(project["common_vdd_v"])
        for application_type in ("HP", "LP"):
            nominal = float(config["models"][application_type]["expected_nominal_vdd_v"])
            label = (
                "nominal_vdd"
                if math.isclose(nominal, common_vdd, abs_tol=1e-12)
                else f"common_{format_voltage_for_name(common_vdd)}"
            )
            frame = select_curve(combined, application_type, label)
            curve_key = f"{application_type}.common_vdd"
            row = {
                "application_type": application_type,
                "bias_label": label,
                "comparison_basis": "common_vdd",
                "VDS_V": common_vdd,
                "Ion_definition_VGS_V": common_vdd,
                "Ioff_definition_VGS_V": IOFF_DEFINITION_VGS_V,
                "nominal_VDD_V": nominal,
            }
            row.update(analyze_curve(frame, common_vdd, settings, curve_key))
            row["Ion_A_per_um"] = row["Ion_A"] / width_um
            row["Ioff_A_per_um"] = row["Ioff_A"] / width_um
            rows.append(row)

    metrics = pd.DataFrame(rows, columns=METRICS_COLUMNS)
    output_dir = ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Twelve significant digits retain far more precision than the published
    # tables while suppressing platform-specific last-bit regression noise.
    metrics.to_csv(
        output_dir / "metrics.csv",
        index=False,
        float_format=METRICS_FLOAT_FORMAT,
        lineterminator="\n",
    )
    create_plots(combined, metrics)
    write_comparison_summary(config, metrics)
    return metrics


def create_plots(combined: pd.DataFrame, metrics: pd.DataFrame) -> None:
    figure_dir = ROOT / "results" / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    colors = {"HP": "#D55E00", "LP": "#0072B2"}
    styles = {"low_vds": "--", "nominal_vdd": "-"}

    nominal_and_low = combined[combined["comparison_basis"] != "common_vdd"]
    for logarithmic, filename in (
        (False, "id_vg_linear.png"),
        (True, "id_vg_semilog.png"),
    ):
        fig, ax = plt.subplots(figsize=(8.2, 5.2), constrained_layout=True)
        for (application_type, bias_label), frame in nominal_and_low.groupby(
            ["application_type", "bias_label"], sort=False
        ):
            vds = float(frame["VDS_V"].iloc[0])
            label = f"{application_type}, VDS={vds:g} V"
            ax.plot(
                frame["VGS_V"],
                frame["ID_A"],
                color=colors[application_type],
                linestyle=styles.get(bias_label, ":"),
                linewidth=2,
                label=label,
            )
        if logarithmic:
            ax.set_yscale("log")
            ax.set_ylim(bottom=max(1e-18, nominal_and_low["ID_A"].min() * 0.5))
        ax.set_xlabel("Gate voltage, VGS (V)")
        ax.set_ylabel("Drain current, ID (A)")
        ax.set_title("PTM 45 nm NMOS transfer characteristics")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend()
        fig.savefig(figure_dir / filename, dpi=180)
        plt.close(fig)

    common = metrics[metrics["comparison_basis"] == "common_vdd"]
    if not common.empty:
        fig, axes = plt.subplots(1, 3, figsize=(11, 4), constrained_layout=True)
        labels = common["application_type"].tolist()
        axes[0].bar(labels, common["Ion_A_per_um"] * 1e6, color=[colors[x] for x in labels])
        axes[0].set_ylabel("Ion (uA/um)")
        axes[0].set_title("On current")
        axes[1].bar(labels, common["Ioff_A_per_um"], color=[colors[x] for x in labels])
        axes[1].set_yscale("log")
        axes[1].set_ylabel("Ioff (A/um)")
        axes[1].set_title("Off current")
        axes[2].bar(labels, common["SS_mV_dec"], color=[colors[x] for x in labels])
        axes[2].set_ylabel("Minimum local SS (mV/dec)")
        axes[2].set_title("Minimum local SS")
        for ax in axes:
            ax.grid(True, axis="y", alpha=0.25)
        fig.suptitle("HP-LP comparison at a common supply voltage")
        fig.savefig(figure_dir / "hp_lp_common_vdd_metrics.png", dpi=180)
        plt.close(fig)


def write_comparison_summary(config: dict[str, Any], metrics: pd.DataFrame) -> None:
    lines = [
        "# Metric extraction summary",
        "",
        "Ion and Ioff are extracted at the exact endpoint definitions shown in "
        "`metrics.csv`. SS is the minimum sliding-window linear-regression value "
        "in log10(ID)-VGS space; the selected range, point count, and R-squared are "
        "stored alongside the result.",
        "",
        "## Model-nominal conditions",
        "",
        "The HP and LP nominal results use different supply voltages (1.0 V and "
        "1.1 V). They describe each model at its intended nominal condition, but "
        "their Ion difference is not attributable to model type alone.",
        "",
    ]
    nominal = metrics[metrics["comparison_basis"] == "model_nominal_vdd"]
    lines.extend(metrics_markdown_table(nominal))

    common = metrics[metrics["comparison_basis"] == "common_vdd"]
    if not common.empty:
        vdd = float(config["project"]["common_vdd_v"])
        lines.extend(
            [
                "",
                f"## Common-voltage comparison ({vdd:g} V)",
                "",
                "This section holds VGS and VDS constant, so it is the primary "
                "bias-aligned descriptive HP-LP model comparison.",
                "",
            ]
        )
        lines.extend(metrics_markdown_table(common))
        hp = common[common["application_type"] == "HP"].iloc[0]
        lp = common[common["application_type"] == "LP"].iloc[0]
        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                f"- HP Ion is {hp['Ion_A_per_um'] / lp['Ion_A_per_um']:.3f}x LP "
                "at the tested DC bias. Capacitance and circuit delay were not evaluated.",
                f"- HP Ioff is {hp['Ioff_A_per_um'] / lp['Ioff_A_per_um']:.2f}x LP; "
                "LP therefore has lower static leakage under this condition.",
                f"- LP Ion/Ioff is {lp['Ion_Ioff_ratio'] / hp['Ion_Ioff_ratio']:.2f}x HP; "
                "this DC ratio is not a measurement of total power.",
                f"- The minimum-local-SS gap is "
                f"{abs(hp['SS_mV_dec'] - lp['SS_mV_dec']):.3f} mV/dec. "
                "Under this project's descriptive <=5% criterion, the bundled "
                "sensitivity analysis supports treating the values as similar across "
                "the tested extraction settings. This is not a statistical equivalence test.",
                "",
                "These are nominal PTM simulation results, not measured-wafer or "
                "process-yield results.",
            ]
        )

    (ROOT / "results" / "comparison_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def metrics_markdown_table(frame: pd.DataFrame) -> list[str]:
    lines = [
        "| Model | VDS (V) | Ion (uA/um) | Ioff (A/um) | Ion/Ioff | Minimum local SS (mV/dec) | Local-fit R2 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in frame.iterrows():
        lines.append(
            f"| {row['application_type']} | {row['VDS_V']:.3g} | "
            f"{row['Ion_A_per_um'] * 1e6:.4g} | {row['Ioff_A_per_um']:.4e} | "
            f"{row['Ion_Ioff_ratio']:.4e} | {row['SS_mV_dec']:.3f} | "
            f"{row['SS_fit_R_squared']:.6f} |"
        )
    return lines


def generate_synthetic_data(config: dict[str, Any]) -> pd.DataFrame:
    project = config["project"]
    step = float(project["vgs_step_v"])
    vdd = 1.0
    vgs = np.arange(0.0, vdd + step / 2, step)
    target_ss_v_dec = 0.080
    target_ion_a = 1.0e-3
    target_ioff_a = 1.0e-10

    exponential = target_ioff_a * np.power(10.0, vgs / target_ss_v_dec)
    # Smoothly approach Ion without changing the low-current exponential slope.
    clean_id = 1.0 / (1.0 / exponential + 1.0 / target_ion_a)
    rng = np.random.default_rng(45)
    observed_id = clean_id * np.exp(rng.normal(0.0, 0.015, size=len(vgs)))
    outlier_indices = np.array([55, 125])
    observed_id[outlier_indices] *= np.array([4.0, 0.25])
    is_outlier = np.zeros(len(vgs), dtype=bool)
    is_outlier[outlier_indices] = True

    frame = pd.DataFrame(
        {
            "model_family": "synthetic_validation",
            "device_type": "NMOS-like",
            "technology_nm": np.nan,
            "application_type": "VALIDATION",
            "W_um": 1.0,
            "L_um": np.nan,
            "temperature_C": 25.0,
            "VDS_V": vdd,
            "VGS_V": vgs,
            "ID_A": observed_id,
            "ID_clean_A": clean_id,
            "is_injected_outlier": is_outlier,
            "target_SS_mV_dec": target_ss_v_dec * 1000,
            "target_Ion_A": target_ion_a,
            "target_Ioff_A": target_ioff_a,
            "source_type": "synthetic_code_validation",
            "simulator": "python",
        }
    )
    output = ROOT / "data" / "synthetic" / "synthetic_validation_data.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return frame


def doctor(config: dict[str, Any], ngspice_arg: str | None) -> dict[str, ModelInfo]:
    models = validate_models(config)
    executable = find_ngspice(ngspice_arg)
    completed = subprocess.run(
        [executable, "--version"], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise PipelineError("ngspice exists but '--version' failed.")
    version_output = (completed.stdout or completed.stderr).decode(
        "utf-8", errors="replace"
    )
    version_line = version_output.splitlines()
    print(f"ngspice: {version_line[0] if version_line else executable}")
    for application_type, model in models.items():
        print(
            f"{application_type}: model={model.model_name}, "
            f"nominal VDD={model.nominal_vdd_v:g} V, SHA-256={model.sha256[:12]}..."
        )
    return models


def load_processed() -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "ptm45_combined.csv"
    if not path.is_file():
        raise PipelineError(f"Missing {path.relative_to(ROOT)}. Run 'process' first.")
    # Preserve the decimal strings emitted by the simulation run closely enough
    # for a standalone ``analyze`` rerun to reproduce the bundled metrics.
    return pd.read_csv(path, float_precision="round_trip")


def command_all(config: dict[str, Any], ngspice_arg: str | None) -> None:
    models = doctor(config, ngspice_arg)
    specs = generate_netlists(config, models)
    run_ngspice(specs, find_ngspice(ngspice_arg))
    combined = process_raw_data(config, specs)
    metrics = analyze_data(config, combined)
    generate_synthetic_data(config)
    print(
        f"Completed: {len(specs)} curves, {len(combined)} data rows, "
        f"{len(metrics)} metric rows."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "doctor",
            "generate-netlists",
            "simulate",
            "process",
            "analyze",
            "synthetic",
            "all",
        ),
    )
    parser.add_argument(
        "--ngspice",
        help="Path to the ngspice executable when it is not available on PATH.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    try:
        if args.command == "doctor":
            doctor(config, args.ngspice)
        elif args.command == "generate-netlists":
            models = validate_models(config)
            specs = generate_netlists(config, models)
            print(f"Generated {len(specs)} netlists.")
        elif args.command == "simulate":
            models = validate_models(config)
            specs = generate_netlists(config, models)
            run_ngspice(specs, find_ngspice(args.ngspice))
            print(f"Generated {len(specs)} raw data files.")
        elif args.command == "process":
            models = validate_models(config)
            specs = build_sweep_specs(config, models)
            combined = process_raw_data(config, specs)
            print(f"Wrote {len(combined)} processed rows.")
        elif args.command == "analyze":
            metrics = analyze_data(config, load_processed())
            print(f"Wrote {len(metrics)} metric rows and figures.")
        elif args.command == "synthetic":
            frame = generate_synthetic_data(config)
            print(f"Wrote {len(frame)} synthetic validation rows.")
        elif args.command == "all":
            command_all(config, args.ngspice)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
