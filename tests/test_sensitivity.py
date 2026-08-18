from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ss_sensitivity import generate_tables, summarize


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SensitivityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        combined = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "ptm45_combined.csv"
        )
        metrics = pd.read_csv(PROJECT_ROOT / "results" / "metrics.csv")
        cls.windows, cls.sensitivity, cls.cutoff = generate_tables(combined, metrics)

    def test_reconstructed_inventory_and_headline_values(self) -> None:
        self.assertEqual(len(self.windows), 728)
        self.assertEqual(
            self.windows.groupby("application_type").size().to_dict(),
            {"HP": 276, "LP": 452},
        )
        summary = summarize(self.sensitivity)
        self.assertEqual(summary["total"], 72)
        self.assertEqual(summary["valid"], 60)
        self.assertEqual(summary["not_applicable"], 12)
        self.assertEqual(summary["edge_contacts"], 0)
        self.assertAlmostEqual(
            summary["max_paired_symmetric_difference_pct"], 1.440339, places=5
        )

        valid = self.sensitivity[self.sensitivity["status"] == "VALID"]
        hp = valid[valid["application_type"] == "HP"]
        lp = valid[valid["application_type"] == "LP"]
        self.assertTrue(np.isclose(hp["SS_mV_dec"].min(), 87.3354749278))
        self.assertTrue(np.isclose(hp["SS_mV_dec"].max(), 88.2102051322))
        self.assertTrue(np.isclose(lp["SS_mV_dec"].min(), 86.3334386819))
        self.assertTrue(np.isclose(lp["SS_mV_dec"].max(), 86.9487632708))

    def test_current_ceiling_candidate_counts_and_intervals(self) -> None:
        self.assertEqual(len(self.cutoff), 10)
        self.assertEqual(
            self.cutoff[self.cutoff["application_type"] == "HP"][
                "candidate_count"
            ].tolist(),
            [42, 52, 63, 75, 83],
        )
        self.assertEqual(
            self.cutoff[self.cutoff["application_type"] == "LP"][
                "candidate_count"
            ].tolist(),
            [78, 87, 99, 110, 121],
        )
        for _, frame in self.cutoff.groupby("application_type"):
            self.assertEqual(frame["VGS_min_V"].nunique(), 1)
            self.assertEqual(frame["VGS_max_V"].nunique(), 1)
            self.assertFalse(
                frame["touches_lower_sweep_edge"].fillna(False).astype(bool).any()
            )


if __name__ == "__main__":
    unittest.main()
