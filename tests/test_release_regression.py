from __future__ import annotations

import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BundledResultRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.combined = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "ptm45_combined.csv"
        )
        cls.metrics = pd.read_csv(PROJECT_ROOT / "results" / "metrics.csv")
        cls.manifest = pd.read_csv(
            PROJECT_ROOT / "data" / "metadata" / "data_manifest.csv"
        )

    def test_extended_sweep_inventory(self) -> None:
        self.assertEqual(len(self.combined), 1245)
        self.assertEqual(len(self.manifest), 5)
        self.assertEqual(int(self.manifest["row_count"].sum()), 1245)
        self.assertTrue(np.allclose(self.manifest["VGS_start_V"], -0.2))
        self.assertEqual(
            sorted(self.manifest["row_count"].astype(int).tolist()),
            [241, 241, 241, 261, 261],
        )

    def test_curve_integrity(self) -> None:
        self.assertFalse(self.combined[["VGS_V", "ID_A"]].isna().any().any())
        self.assertTrue((self.combined["ID_A"] > 0).all())
        curve_keys = ["application_type", "bias_label", "VDS_V"]
        self.assertFalse(self.combined.duplicated(curve_keys + ["VGS_V"]).any())
        for _, frame in self.combined.groupby(curve_keys, sort=False):
            vgs = frame.sort_values("VGS_V")["VGS_V"].to_numpy(dtype=float)
            self.assertAlmostEqual(float(vgs[0]), -0.2, places=12)
            self.assertTrue(np.allclose(np.diff(vgs), 0.005, atol=1e-12))

    def test_metrics_schema_and_common_vdd_values(self) -> None:
        self.assertEqual(len(self.metrics), 4)
        self.assertIn("Ioff_definition_VGS_V", self.metrics.columns)
        self.assertTrue(np.allclose(self.metrics["Ioff_definition_VGS_V"], 0.0))

        common = self.metrics[self.metrics["comparison_basis"] == "common_vdd"]
        self.assertEqual(set(common["application_type"]), {"HP", "LP"})
        hp = common[common["application_type"] == "HP"].iloc[0]
        lp = common[common["application_type"] == "LP"].iloc[0]
        self.assertTrue(np.isclose(hp["Ion_A"], 1.339206241155616e-3, rtol=1e-12))
        self.assertTrue(np.isclose(lp["Ion_A"], 4.019845680949588e-4, rtol=1e-12))
        self.assertTrue(np.isclose(hp["SS_mV_dec"], 87.50593064481782, rtol=1e-12))
        self.assertTrue(np.isclose(lp["SS_mV_dec"], 86.64802452741170, rtol=1e-12))
        self.assertTrue((common["SS_fit_VGS_min_V"] > -0.2).all())

    def test_release_artifacts_are_present(self) -> None:
        required = [
            PROJECT_ROOT / "results" / "comparison_summary.md",
            PROJECT_ROOT / "results" / "figures" / "id_vg_linear.png",
            PROJECT_ROOT / "results" / "figures" / "id_vg_semilog.png",
            PROJECT_ROOT / "results" / "figures" / "hp_lp_common_vdd_metrics.png",
            PROJECT_ROOT
            / "results"
            / "validation"
            / "PTM45_Excel_Cross_Implementation_Check.xlsx",
            PROJECT_ROOT
            / "results"
            / "validation"
            / "PTM45_SS_Sensitivity_Analysis.xlsx",
            PROJECT_ROOT
            / "results"
            / "validation"
            / "all_window_statistics.csv",
            PROJECT_ROOT
            / "results"
            / "validation"
            / "sensitivity_results.csv",
            PROJECT_ROOT
            / "results"
            / "validation"
            / "cutoff_sensitivity.csv",
        ]
        for path in required:
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)

        workbook_expectations = {
            "PTM45_Excel_Cross_Implementation_Check.xlsx": b"Cross-Implementation",
            "PTM45_SS_Sensitivity_Analysis.xlsx": b"Reproduction command",
        }
        for filename, expected_text in workbook_expectations.items():
            path = PROJECT_ROOT / "results" / "validation" / filename
            with self.subTest(workbook=filename), ZipFile(path) as archive:
                names = archive.namelist()
                self.assertFalse(any(name.startswith("xl/externalLinks/") for name in names))
                self.assertNotIn("xl/vbaProject.bin", names)
                xml_text = b"".join(
                    archive.read(name)
                    for name in names
                    if name.startswith("xl/") and name.endswith(".xml")
                )
                self.assertIn(expected_text, xml_text)


if __name__ == "__main__":
    unittest.main()
