from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

from verify_release import (  # noqa: E402
    VTH_DIBL_EXACT_COLUMNS,
    VTH_DIBL_ROW_KEY_COLUMNS,
    ReleaseIntegrityError,
    compare_metric_frames,
    compare_result_frames,
    find_forbidden_artifacts,
    recompute_metrics,
    recompute_vth_dibl,
    verify_bundled_metrics,
    verify_bundled_vth_dibl,
    verify_forbidden_artifacts_absent,
    verify_manifest,
)

from ptm_pipeline import VTH_DIBL_COLUMNS  # noqa: E402


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManifestVerificationTests(unittest.TestCase):
    def test_accepts_complete_manifest_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data = root / "data.csv"
            data.write_text("x,y\n1,2\n", encoding="utf-8")
            manifest = root / "RELEASE_MANIFEST.sha256"
            manifest.write_text(
                f"{file_digest(data)}  ./data.csv\n", encoding="utf-8"
            )

            entries = verify_manifest(root, manifest, require_complete=True)
            self.assertEqual(len(entries), 1)

            data.write_text("x,y\n1,3\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseIntegrityError, "hash mismatch"):
                verify_manifest(root, manifest, require_complete=True)

    def test_rejects_unlisted_and_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            listed = root / "listed.txt"
            listed.write_text("listed\n", encoding="utf-8")
            (root / "unlisted.txt").write_text("unlisted\n", encoding="utf-8")
            manifest = root / "RELEASE_MANIFEST.sha256"
            manifest.write_text(
                f"{file_digest(listed)}  ./listed.txt\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ReleaseIntegrityError, "not listed"):
                verify_manifest(root, manifest, require_complete=True)

            manifest.write_text(f"{'0' * 64}  ./../escape.txt\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseIntegrityError, "Unsafe manifest path"):
                verify_manifest(root, manifest)


class PublicBundleTests(unittest.TestCase):
    def test_bundled_release_has_no_private_or_generated_files(self) -> None:
        verify_forbidden_artifacts_absent(PROJECT_ROOT)

    def test_detects_each_forbidden_artifact_class(self) -> None:
        cases = {
            "model card": Path("models/45nm_HP.pm"),
            "runtime cache": Path("results/.matplotlib-cache/fontlist-v390.json"),
            "generated netlist": Path("netlists/generated/ptm45_hp.cir"),
            "raw simulator output": Path("data/raw/ptm45_hp_raw.txt"),
            "simulator log": Path("results/logs/ptm45_hp.log"),
            "workbook sidecar": Path("results/validation/check.xlsx.inspect.ndjson"),
        }
        for label, relative_path in cases.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    artifact = root / relative_path
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    artifact.write_text("fixture\n", encoding="utf-8")
                    findings = find_forbidden_artifacts(root)
                    self.assertEqual(len(findings), 1)
                    self.assertIn(relative_path.as_posix(), findings[0])


class BundledMetricVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.recalculated = recompute_metrics(PROJECT_ROOT)

    def test_bundled_metrics_match_pipeline_recalculation(self) -> None:
        verified = verify_bundled_metrics(PROJECT_ROOT)
        self.assertEqual(len(verified), 4)

    def test_detects_metric_tampering_outside_tolerance(self) -> None:
        bundled = pd.read_csv(
            PROJECT_ROOT / "results" / "metrics.csv", float_precision="round_trip"
        )
        bundled.loc[0, "Ion_A"] *= 1.01
        with self.assertRaisesRegex(ReleaseIntegrityError, "Ion_A"):
            compare_metric_frames(bundled, self.recalculated)


class BundledVthDiblVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.recalculated, cls.sensitivity = recompute_vth_dibl(PROJECT_ROOT)

    def test_bundled_vth_dibl_tables_match_recalculation(self) -> None:
        metrics, sensitivity = verify_bundled_vth_dibl(PROJECT_ROOT)
        self.assertEqual(len(metrics), 3)
        self.assertEqual(len(sensitivity), 15)

    def test_detects_vth_dibl_tampering_outside_tolerance(self) -> None:
        bundled = pd.read_csv(
            PROJECT_ROOT / "results" / "vth_dibl_metrics.csv",
            float_precision="round_trip",
        )
        bundled.loc[0, "DIBL_mV_per_V"] *= 1.01
        with self.assertRaisesRegex(ReleaseIntegrityError, "DIBL_mV_per_V"):
            compare_result_frames(
                bundled,
                self.recalculated,
                columns=VTH_DIBL_COLUMNS,
                row_key_columns=VTH_DIBL_ROW_KEY_COLUMNS,
                exact_columns=VTH_DIBL_EXACT_COLUMNS,
                label="Vth/DIBL",
            )

    def test_rejects_extra_vth_dibl_columns(self) -> None:
        bundled = pd.read_csv(
            PROJECT_ROOT / "results" / "vth_dibl_metrics.csv",
            float_precision="round_trip",
        )
        bundled["unexpected"] = 1
        with self.assertRaisesRegex(ReleaseIntegrityError, "unexpected schema"):
            compare_result_frames(
                bundled,
                self.recalculated,
                columns=VTH_DIBL_COLUMNS,
                row_key_columns=VTH_DIBL_ROW_KEY_COLUMNS,
                exact_columns=VTH_DIBL_EXACT_COLUMNS,
                label="Vth/DIBL",
            )


if __name__ == "__main__":
    unittest.main()
