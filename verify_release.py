#!/usr/bin/env python3
"""Verify the integrity of the public PTM45 release bundle.

The verifier performs three independent checks without modifying the release:

1. every file named by ``RELEASE_MANIFEST.sha256`` matches its SHA-256 hash;
2. model cards, generated netlists, and runtime-cache files are absent; and
3. the bundled Ion/Ioff/SS and Vth/DIBL tables agree with in-memory
   recalculations from the bundled processed data using the extraction
   functions in ``ptm_pipeline.py``.

Run it from any directory with::

    python verify_release.py
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

# Importing ptm_pipeline also imports Matplotlib. Keep its cache outside the
# release tree so that verification itself cannot create a bundled cache file.
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ptm45-release-mpl-cache")
)

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from ptm_pipeline import (  # noqa: E402
    IOFF_DEFINITION_VGS_V,
    METRICS_COLUMNS,
    VTH_DIBL_COLUMNS,
    VTH_DIBL_SENSITIVITY_COLUMNS,
    PipelineError,
    analyze_curve,
    analyze_vth_dibl,
    analyze_vth_dibl_sensitivity,
    format_voltage_for_name,
    load_config,
    select_curve,
)


MANIFEST_LINE_RE = re.compile(r"^([0-9A-Fa-f]{64}) ([ *])(.+)$")
ROW_KEY_COLUMNS = ("application_type", "bias_label", "comparison_basis")
EXACT_METRIC_COLUMNS = (
    "application_type",
    "bias_label",
    "comparison_basis",
    "SS_fit_points",
    "SS_method",
)
VTH_DIBL_ROW_KEY_COLUMNS = ("application_type", "comparison_basis")
VTH_DIBL_EXACT_COLUMNS = (
    "application_type",
    "comparison_basis",
    "low_bias_label",
    "high_bias_label",
    "Vth_method",
    "Vth_interpolation",
)
VTH_DIBL_SENSITIVITY_ROW_KEY_COLUMNS = (
    "application_type",
    "comparison_basis",
    "Vth_current_multiplier",
)
VTH_DIBL_SENSITIVITY_EXACT_COLUMNS = VTH_DIBL_EXACT_COLUMNS
CACHE_DIRECTORY_NAMES = {
    ".matplotlib-cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}


class ReleaseIntegrityError(RuntimeError):
    """A release-integrity check failed."""


@dataclass(frozen=True)
class ManifestEntry:
    """One normalized SHA-256 manifest entry."""

    sha256: str
    relative_path: PurePosixPath


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for *path*."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(manifest_path: Path) -> list[ManifestEntry]:
    """Parse a GNU ``sha256sum``-style manifest and reject unsafe paths."""

    if not manifest_path.is_file():
        raise ReleaseIntegrityError(f"Manifest not found: {manifest_path}")

    entries: list[ManifestEntry] = []
    seen_paths: set[PurePosixPath] = set()
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        match = MANIFEST_LINE_RE.fullmatch(raw_line)
        if not match:
            raise ReleaseIntegrityError(
                f"Malformed manifest line {line_number}: {raw_line!r}"
            )

        digest, _, raw_path = match.groups()
        if raw_path.startswith("./"):
            raw_path = raw_path[2:]
        relative_path = PurePosixPath(raw_path)
        if (
            not raw_path
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or "." in relative_path.parts
        ):
            raise ReleaseIntegrityError(
                f"Unsafe manifest path on line {line_number}: {raw_path!r}"
            )
        if relative_path in seen_paths:
            raise ReleaseIntegrityError(
                f"Duplicate manifest path on line {line_number}: {relative_path}"
            )
        seen_paths.add(relative_path)
        entries.append(ManifestEntry(digest.lower(), relative_path))

    if not entries:
        raise ReleaseIntegrityError("Manifest contains no file entries.")
    return entries


def _release_files(root: Path, manifest_path: Path) -> set[PurePosixPath]:
    """Return release files, excluding the manifest itself and local Git data."""

    root = root.resolve()
    manifest_path = manifest_path.resolve()
    paths: set[PurePosixPath] = set()
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts:
            continue
        if not (path.is_file() or path.is_symlink()):
            continue
        if path.resolve() == manifest_path:
            continue
        paths.add(PurePosixPath(path.relative_to(root).as_posix()))
    return paths


def verify_manifest(
    root: Path,
    manifest_path: Path | None = None,
    *,
    require_complete: bool = False,
) -> list[ManifestEntry]:
    """Verify manifest hashes and optionally require coverage of every file."""

    root = root.resolve()
    manifest_path = (manifest_path or root / "RELEASE_MANIFEST.sha256").resolve()
    entries = parse_manifest(manifest_path)
    failures: list[str] = []

    try:
        manifest_path.relative_to(root)
    except ValueError as exc:
        raise ReleaseIntegrityError("Manifest must be inside the release root.") from exc

    for entry in entries:
        candidate = root.joinpath(*entry.relative_path.parts)
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            failures.append(f"path escapes release root: {entry.relative_path}")
            continue
        if candidate.is_symlink():
            failures.append(f"manifest entry is a symlink: {entry.relative_path}")
            continue
        if not candidate.is_file():
            failures.append(f"missing file: {entry.relative_path}")
            continue
        actual = sha256_file(candidate)
        if actual != entry.sha256:
            failures.append(
                f"hash mismatch: {entry.relative_path} "
                f"(expected {entry.sha256}, got {actual})"
            )

    if require_complete:
        listed = {entry.relative_path for entry in entries}
        actual_files = _release_files(root, manifest_path)
        for path in sorted(actual_files - listed, key=str):
            failures.append(f"file is not listed in manifest: {path}")
        for path in sorted(listed - actual_files, key=str):
            # Missing files have already been reported above. This wording also
            # covers an unusual path that resolves outside the root.
            if not (root.joinpath(*path.parts).is_file()):
                failures.append(f"manifest lists no release file: {path}")

    if failures:
        raise ReleaseIntegrityError(
            "Manifest verification failed:\n- " + "\n- ".join(failures)
        )
    return entries


def find_forbidden_artifacts(root: Path) -> list[str]:
    """Return private/generated artifacts that must not be in a public bundle."""

    root = root.resolve()
    findings: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        parts = relative.parts
        if ".git" in parts:
            continue
        # Empty cache/generated directories are not files and therefore are not
        # present in a ZIP or Git tree. Only distributable artifacts are flagged.
        if not (path.is_file() or path.is_symlink()):
            continue

        lower_parts = tuple(part.lower() for part in parts)
        lower_name = path.name.lower()
        reason: str | None = None
        if lower_parts and lower_parts[0] == "models" and lower_name != "readme.md":
            reason = "model-card candidate"
        elif any(part in CACHE_DIRECTORY_NAMES for part in parts):
            reason = "runtime cache"
        elif path.suffix.lower() in CACHE_FILE_SUFFIXES:
            reason = "compiled Python cache"
        elif lower_name.startswith("fontlist-v") and path.suffix.lower() == ".json":
            reason = "Matplotlib font cache"
        elif len(lower_parts) >= 2 and lower_parts[:2] == ("netlists", "generated"):
            reason = "generated netlist artifact"
        elif lower_parts and lower_parts[0] == "netlists" and path.suffix.lower() == ".cir":
            reason = "generated netlist artifact"
        elif (
            len(lower_parts) >= 2
            and lower_parts[:2] == ("data", "raw")
            and lower_name != "readme.md"
        ):
            reason = "raw simulator artifact"
        elif (
            len(lower_parts) >= 2
            and lower_parts[:2] == ("results", "logs")
            and lower_name != "readme.md"
        ):
            reason = "simulator log artifact"
        elif lower_name.endswith(".inspect.ndjson") or lower_name.startswith("~$"):
            reason = "temporary workbook artifact"
        elif path.is_symlink():
            reason = "symlink"

        if reason:
            findings.append(f"{relative.as_posix()} ({reason})")
    return sorted(findings)


def verify_forbidden_artifacts_absent(root: Path) -> None:
    """Raise when a private/generated release artifact is found."""

    findings = find_forbidden_artifacts(root)
    if findings:
        raise ReleaseIntegrityError(
            "Forbidden release artifacts found:\n- " + "\n- ".join(findings)
        )


def recompute_metrics(root: Path) -> pd.DataFrame:
    """Recalculate metrics in memory with the public pipeline's analysis logic."""

    root = root.resolve()
    config = load_config(root / "project_config.json")
    combined_path = root / "data" / "processed" / "ptm45_combined.csv"
    if not combined_path.is_file():
        raise ReleaseIntegrityError(f"Processed data not found: {combined_path}")
    combined = pd.read_csv(combined_path, float_precision="round_trip")
    settings = config["ss_extraction"]
    width_um = float(config["project"]["width_um"])
    rows: list[dict[str, object]] = []

    for application_type in ("HP", "LP"):
        frame = select_curve(combined, application_type, "nominal_vdd")
        nominal_vdd = float(frame["nominal_VDD_V"].iloc[0])
        row: dict[str, object] = {
            "application_type": application_type,
            "bias_label": "nominal_vdd",
            "comparison_basis": "model_nominal_vdd",
            "VDS_V": nominal_vdd,
            "Ion_definition_VGS_V": nominal_vdd,
            "Ioff_definition_VGS_V": IOFF_DEFINITION_VGS_V,
            "nominal_VDD_V": nominal_vdd,
        }
        row.update(
            analyze_curve(
                frame,
                nominal_vdd,
                settings,
                f"{application_type}.nominal_vdd",
            )
        )
        row["Ion_A_per_um"] = float(row["Ion_A"]) / width_um
        row["Ioff_A_per_um"] = float(row["Ioff_A"]) / width_um
        rows.append(row)

    project = config["project"]
    if bool(project.get("include_common_vdd_curve", False)):
        common_vdd = float(project["common_vdd_v"])
        for application_type in ("HP", "LP"):
            nominal_vdd = float(
                config["models"][application_type]["expected_nominal_vdd_v"]
            )
            bias_label = (
                "nominal_vdd"
                if math.isclose(nominal_vdd, common_vdd, abs_tol=1e-12)
                else f"common_{format_voltage_for_name(common_vdd)}"
            )
            frame = select_curve(combined, application_type, bias_label)
            row = {
                "application_type": application_type,
                "bias_label": bias_label,
                "comparison_basis": "common_vdd",
                "VDS_V": common_vdd,
                "Ion_definition_VGS_V": common_vdd,
                "Ioff_definition_VGS_V": IOFF_DEFINITION_VGS_V,
                "nominal_VDD_V": nominal_vdd,
            }
            row.update(
                analyze_curve(
                    frame,
                    common_vdd,
                    settings,
                    f"{application_type}.common_vdd",
                )
            )
            row["Ion_A_per_um"] = float(row["Ion_A"]) / width_um
            row["Ioff_A_per_um"] = float(row["Ioff_A"]) / width_um
            rows.append(row)

    return pd.DataFrame(rows, columns=METRICS_COLUMNS)


def _row_key(row: pd.Series) -> tuple[str, ...]:
    return tuple(str(row[column]) for column in ROW_KEY_COLUMNS)


def compare_metric_frames(
    bundled: pd.DataFrame,
    recalculated: pd.DataFrame,
    *,
    rtol: float = 1e-10,
    atol: float = 1e-15,
) -> None:
    """Compare metric frames by stable row keys and numeric tolerances."""

    missing_columns = [column for column in METRICS_COLUMNS if column not in bundled]
    if missing_columns:
        raise ReleaseIntegrityError(
            "Bundled metrics are missing columns: " + ", ".join(missing_columns)
        )
    if list(bundled.columns) != METRICS_COLUMNS:
        raise ReleaseIntegrityError("Bundled metrics have an unexpected schema.")
    if list(recalculated.columns) != METRICS_COLUMNS:
        raise ReleaseIntegrityError("Recalculated metrics have an unexpected schema.")

    def index_rows(frame: pd.DataFrame, label: str) -> dict[tuple[str, ...], pd.Series]:
        rows: dict[tuple[str, ...], pd.Series] = {}
        for _, row in frame.iterrows():
            key = _row_key(row)
            if key in rows:
                raise ReleaseIntegrityError(f"Duplicate {label} metric row: {key}")
            rows[key] = row
        return rows

    expected_rows = index_rows(bundled, "bundled")
    actual_rows = index_rows(recalculated, "recalculated")
    if expected_rows.keys() != actual_rows.keys():
        missing = sorted(expected_rows.keys() - actual_rows.keys())
        extra = sorted(actual_rows.keys() - expected_rows.keys())
        raise ReleaseIntegrityError(
            f"Metric row-key mismatch; missing recalculations={missing}, extra={extra}"
        )

    failures: list[str] = []
    numeric_columns = [
        column for column in METRICS_COLUMNS if column not in EXACT_METRIC_COLUMNS
    ]
    for key in sorted(expected_rows):
        expected = expected_rows[key]
        actual = actual_rows[key]
        for column in EXACT_METRIC_COLUMNS:
            if str(expected[column]) != str(actual[column]):
                failures.append(
                    f"{key} {column}: expected {expected[column]!r}, "
                    f"recalculated {actual[column]!r}"
                )
        for column in numeric_columns:
            try:
                expected_value = float(expected[column])
                actual_value = float(actual[column])
            except (TypeError, ValueError):
                failures.append(f"{key} {column}: non-numeric value")
                continue
            if not (
                math.isfinite(expected_value)
                and math.isfinite(actual_value)
                and math.isclose(
                    expected_value,
                    actual_value,
                    rel_tol=rtol,
                    abs_tol=atol,
                )
            ):
                failures.append(
                    f"{key} {column}: expected {expected_value:.17g}, "
                    f"recalculated {actual_value:.17g}"
                )

    if failures:
        raise ReleaseIntegrityError(
            "Bundled metric verification failed:\n- " + "\n- ".join(failures)
        )


def verify_bundled_metrics(
    root: Path, *, rtol: float = 1e-10, atol: float = 1e-15
) -> pd.DataFrame:
    """Recalculate and compare the release's bundled metrics."""

    metrics_path = root.resolve() / "results" / "metrics.csv"
    if not metrics_path.is_file():
        raise ReleaseIntegrityError(f"Bundled metrics not found: {metrics_path}")
    bundled = pd.read_csv(metrics_path, float_precision="round_trip")
    recalculated = recompute_metrics(root)
    compare_metric_frames(bundled, recalculated, rtol=rtol, atol=atol)
    return recalculated


def compare_result_frames(
    bundled: pd.DataFrame,
    recalculated: pd.DataFrame,
    *,
    columns: list[str],
    row_key_columns: tuple[str, ...],
    exact_columns: tuple[str, ...],
    label: str,
    rtol: float = 1e-10,
    atol: float = 1e-15,
) -> None:
    """Compare a bundled result table with an independently recalculated one."""
    missing_columns = [column for column in columns if column not in bundled]
    if missing_columns:
        raise ReleaseIntegrityError(
            f"Bundled {label} results are missing columns: "
            + ", ".join(missing_columns)
        )
    if list(bundled.columns) != columns:
        raise ReleaseIntegrityError(
            f"Bundled {label} results have an unexpected schema."
        )
    if list(recalculated.columns) != columns:
        raise ReleaseIntegrityError(
            f"Recalculated {label} results have an unexpected schema."
        )

    def index_rows(
        frame: pd.DataFrame, source: str
    ) -> dict[tuple[str, ...], pd.Series]:
        rows: dict[tuple[str, ...], pd.Series] = {}
        for _, row in frame.iterrows():
            key = tuple(str(row[column]) for column in row_key_columns)
            if key in rows:
                raise ReleaseIntegrityError(
                    f"Duplicate {source} {label} row: {key}"
                )
            rows[key] = row
        return rows

    expected_rows = index_rows(bundled, "bundled")
    actual_rows = index_rows(recalculated, "recalculated")
    if expected_rows.keys() != actual_rows.keys():
        missing = sorted(expected_rows.keys() - actual_rows.keys())
        extra = sorted(actual_rows.keys() - expected_rows.keys())
        raise ReleaseIntegrityError(
            f"{label} row-key mismatch; missing recalculations={missing}, "
            f"extra={extra}"
        )

    failures: list[str] = []
    numeric_columns = [
        column for column in columns if column not in exact_columns
    ]
    for key in sorted(expected_rows):
        expected = expected_rows[key]
        actual = actual_rows[key]
        for column in exact_columns:
            if str(expected[column]) != str(actual[column]):
                failures.append(
                    f"{key} {column}: expected {expected[column]!r}, "
                    f"recalculated {actual[column]!r}"
                )
        for column in numeric_columns:
            try:
                expected_value = float(expected[column])
                actual_value = float(actual[column])
            except (TypeError, ValueError):
                failures.append(f"{key} {column}: non-numeric value")
                continue
            if not (
                math.isfinite(expected_value)
                and math.isfinite(actual_value)
                and math.isclose(
                    expected_value,
                    actual_value,
                    rel_tol=rtol,
                    abs_tol=atol,
                )
            ):
                failures.append(
                    f"{key} {column}: expected {expected_value:.17g}, "
                    f"recalculated {actual_value:.17g}"
                )

    if failures:
        raise ReleaseIntegrityError(
            f"Bundled {label} verification failed:\n- "
            + "\n- ".join(failures)
        )


def recompute_vth_dibl(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recalculate the base and sensitivity Vth/DIBL result tables."""
    root = root.resolve()
    config = load_config(root / "project_config.json")
    combined_path = root / "data" / "processed" / "ptm45_combined.csv"
    if not combined_path.is_file():
        raise ReleaseIntegrityError(f"Processed data not found: {combined_path}")
    combined = pd.read_csv(combined_path, float_precision="round_trip")
    return (
        analyze_vth_dibl(config, combined),
        analyze_vth_dibl_sensitivity(config, combined),
    )


def verify_bundled_vth_dibl(
    root: Path, *, rtol: float = 1e-10, atol: float = 1e-15
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Verify the bundled base and sensitivity Vth/DIBL tables."""
    result_dir = root.resolve() / "results"
    metrics_path = result_dir / "vth_dibl_metrics.csv"
    sensitivity_path = result_dir / "vth_dibl_sensitivity.csv"
    for path in (metrics_path, sensitivity_path):
        if not path.is_file():
            raise ReleaseIntegrityError(f"Bundled Vth/DIBL result not found: {path}")

    bundled_metrics = pd.read_csv(metrics_path, float_precision="round_trip")
    bundled_sensitivity = pd.read_csv(
        sensitivity_path, float_precision="round_trip"
    )
    recalculated_metrics, recalculated_sensitivity = recompute_vth_dibl(root)
    compare_result_frames(
        bundled_metrics,
        recalculated_metrics,
        columns=VTH_DIBL_COLUMNS,
        row_key_columns=VTH_DIBL_ROW_KEY_COLUMNS,
        exact_columns=VTH_DIBL_EXACT_COLUMNS,
        label="Vth/DIBL",
        rtol=rtol,
        atol=atol,
    )
    compare_result_frames(
        bundled_sensitivity,
        recalculated_sensitivity,
        columns=VTH_DIBL_SENSITIVITY_COLUMNS,
        row_key_columns=VTH_DIBL_SENSITIVITY_ROW_KEY_COLUMNS,
        exact_columns=VTH_DIBL_SENSITIVITY_EXACT_COLUMNS,
        label="Vth/DIBL sensitivity",
        rtol=rtol,
        atol=atol,
    )
    return recalculated_metrics, recalculated_sensitivity


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="release root (default: directory containing this script)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest path (default: ROOT/RELEASE_MANIFEST.sha256)",
    )
    parser.add_argument("--rtol", type=float, default=1e-10)
    parser.add_argument("--atol", type=float, default=1e-15)
    parser.add_argument(
        "--allow-unlisted-files",
        action="store_true",
        help="verify listed hashes without requiring complete manifest coverage",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else root / "RELEASE_MANIFEST.sha256"
    )
    try:
        entries = verify_manifest(
            root,
            manifest_path,
            require_complete=not args.allow_unlisted_files,
        )
        verify_forbidden_artifacts_absent(root)
        metrics = verify_bundled_metrics(root, rtol=args.rtol, atol=args.atol)
        vth_dibl, vth_dibl_sensitivity = verify_bundled_vth_dibl(
            root, rtol=args.rtol, atol=args.atol
        )
    except (
        OSError,
        ValueError,
        KeyError,
        PipelineError,
        ReleaseIntegrityError,
    ) as exc:
        print(f"RELEASE VERIFICATION FAILED\n{exc}", file=sys.stderr)
        return 1

    print(f"PASS manifest: {len(entries)} files")
    print("PASS public bundle: no model cards, caches, or generated netlists")
    print(f"PASS metrics: {len(metrics)} rows recalculated within tolerance")
    print(
        "PASS Vth/DIBL: "
        f"{len(vth_dibl)} base rows and "
        f"{len(vth_dibl_sensitivity)} sensitivity rows recalculated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
