from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ptm_pipeline import (  # noqa: E402
    ModelInfo,
    PipelineError,
    SweepSpec,
    VTH_DIBL_COLUMNS,
    VTH_DIBL_SENSITIVITY_COLUMNS,
    analyze_data,
    analyze_vth_dibl,
    analyze_vth_dibl_sensitivity,
    build_sweep_specs,
    calculate_dibl_mv_per_v,
    expected_row_count,
    extract_ss,
    extract_vth_constant_current,
    load_config,
    parse_model_metadata,
    parse_wrdata,
    render_netlist,
    sha256_file,
    validate_models,
)


class VthDiblTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(PROJECT_ROOT / "project_config.json")
        cls.combined = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "ptm45_combined.csv"
        )

    def test_vth_uses_log_interpolation_and_width_length_ratio(self) -> None:
        frame = pd.DataFrame(
            {
                "VGS_V": [0.2, 0.3],
                "ID_A": [2e-7, 2e-5],
            }
        )

        vth_v, target_current_a = extract_vth_constant_current(
            frame=frame,
            normalized_current_a=1e-7,
            width_um=1.0,
            length_um=0.05,
            interpolation="log10_id_linear",
        )

        self.assertAlmostEqual(target_current_a, 2e-6)
        self.assertAlmostEqual(vth_v, 0.25)

    def test_vth_rejects_unknown_interpolation(self) -> None:
        frame = pd.DataFrame(
            {
                "VGS_V": [0.2, 0.3],
                "ID_A": [2e-7, 2e-5],
            }
        )

        with self.assertRaises(PipelineError):
            extract_vth_constant_current(
                frame=frame,
                normalized_current_a=1e-7,
                width_um=1.0,
                length_um=0.05,
                interpolation="linear_id",
            )

    def test_vth_rejects_absent_crossing(self) -> None:
        frame = pd.DataFrame(
            {
                "VGS_V": [0.2, 0.3, 0.4],
                "ID_A": [2e-8, 2e-7, 8e-7],
            }
        )

        with self.assertRaisesRegex(PipelineError, "found 0"):
            extract_vth_constant_current(
                frame=frame,
                normalized_current_a=1e-7,
                width_um=1.0,
                length_um=0.05,
                interpolation="log10_id_linear",
            )

    def test_vth_rejects_multiple_crossings(self) -> None:
        frame = pd.DataFrame(
            {
                "VGS_V": [0.2, 0.3, 0.4, 0.5],
                "ID_A": [2e-7, 2e-5, 2e-7, 2e-5],
            }
        )

        with self.assertRaisesRegex(PipelineError, "found 3"):
            extract_vth_constant_current(
                frame=frame,
                normalized_current_a=1e-7,
                width_um=1.0,
                length_um=0.05,
                interpolation="log10_id_linear",
            )

    def test_vth_rejects_downward_or_exact_plus_later_crossing(self) -> None:
        cases = (
            pd.DataFrame(
                {
                    "VGS_V": [0.2, 0.3, 0.4],
                    "ID_A": [3e-6, 1e-6, 3e-6],
                }
            ),
            pd.DataFrame(
                {
                    "VGS_V": [0.2, 0.3, 0.4, 0.5],
                    "ID_A": [2e-7, 2e-6, 2e-7, 2e-5],
                }
            ),
            pd.DataFrame(
                {
                    "VGS_V": [0.2, 0.3, 0.4, 0.5],
                    "ID_A": [2e-7, 2e-6, 2e-6, 2e-5],
                }
            ),
        )
        for frame in cases:
            with self.subTest(current=frame["ID_A"].tolist()):
                with self.assertRaises(PipelineError):
                    extract_vth_constant_current(
                        frame=frame,
                        normalized_current_a=1e-7,
                        width_um=1.0,
                        length_um=0.05,
                        interpolation="log10_id_linear",
                    )

    def test_vth_rejects_nonfinite_data_in_crossing_region(self) -> None:
        frame = pd.DataFrame(
            {
                "VGS_V": [0.2, 0.3, 0.4],
                "ID_A": [2e-7, np.nan, 2e-5],
            }
        )

        with self.assertRaisesRegex(PipelineError, "non-finite"):
            extract_vth_constant_current(
                frame=frame,
                normalized_current_a=1e-7,
                width_um=1.0,
                length_um=0.05,
                interpolation="log10_id_linear",
            )

    def test_dibl_returns_positive_mv_per_v(self) -> None:
        dibl_mv_per_v = calculate_dibl_mv_per_v(
            vth_low_v=0.50,
            vth_high_v=0.40,
            low_vds_v=0.05,
            high_vds_v=1.05,
        )

        self.assertAlmostEqual(dibl_mv_per_v, 100.0)

    def test_dibl_rejects_non_increasing_vds(self) -> None:
        with self.assertRaises(PipelineError):
            calculate_dibl_mv_per_v(
                vth_low_v=0.50,
                vth_high_v=0.40,
                low_vds_v=1.0,
                high_vds_v=0.05,
            )

    def test_bundled_vth_dibl_regression(self) -> None:
        result = analyze_vth_dibl(self.config, self.combined)

        self.assertEqual(list(result.columns), VTH_DIBL_COLUMNS)
        self.assertEqual(len(result), 3)
        self.assertFalse(
            result.duplicated(
                subset=["application_type", "comparison_basis"]
            ).any()
        )

        expected = [
            (
                "HP",
                "common_vdd",
                "nominal_vdd",
                0.323646393618,
                0.184795847050,
                146.158470072,
            ),
            (
                "LP",
                "common_vdd",
                "common_1v",
                0.530393010572,
                0.457564061510,
                76.662051644,
            ),
            (
                "LP",
                "model_nominal_vdd",
                "nominal_vdd",
                0.530393010572,
                0.450641601991,
                75.953722458,
            ),
        ]
        actual = list(
            result[
                [
                    "application_type",
                    "comparison_basis",
                    "high_bias_label",
                    "Vth_low_V",
                    "Vth_high_V",
                    "DIBL_mV_per_V",
                ]
            ].itertuples(index=False, name=None)
        )
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in actual],
            [(row[0], row[1], row[2]) for row in expected],
        )
        for actual_row, expected_row in zip(actual, expected, strict=True):
            self.assertAlmostEqual(actual_row[3], expected_row[3], places=10)
            self.assertAlmostEqual(actual_row[4], expected_row[4], places=10)
            self.assertAlmostEqual(actual_row[5], expected_row[5], places=9)

        np.testing.assert_allclose(
            result["Vth_target_ID_A"].to_numpy(dtype=float),
            np.full(3, 1e-7 * 1.0 / 0.045),
            rtol=1e-12,
            atol=0.0,
        )
        self.assertTrue((result["DIBL_mV_per_V"] > 0).all())

    def test_vth_dibl_rejects_processed_dimension_mismatch(self) -> None:
        mismatches = {
            "W_um": 2.0,
            "L_um": 0.090,
            "temperature_C": 125.0,
        }
        for column, value in mismatches.items():
            with self.subTest(column=column):
                combined = self.combined.copy()
                combined[column] = value
                with self.assertRaisesRegex(PipelineError, column):
                    analyze_vth_dibl(self.config, combined)

    def test_bundled_vth_dibl_sensitivity_structure(self) -> None:
        result = analyze_vth_dibl_sensitivity(self.config, self.combined)
        multipliers = np.asarray(
            self.config["vth_extraction"]["sensitivity_multipliers"],
            dtype=float,
        )
        key_columns = ["application_type", "comparison_basis"]

        self.assertEqual(
            list(result.columns), VTH_DIBL_SENSITIVITY_COLUMNS
        )
        self.assertEqual(len(result), 3 * len(multipliers))
        self.assertEqual(result.groupby(key_columns).ngroups, 3)
        self.assertFalse(
            result.duplicated(
                subset=key_columns + ["Vth_current_multiplier"]
            ).any()
        )

        base_normalized_current = float(
            self.config["vth_extraction"]["normalized_current_a"]
        )
        width_um = float(self.config["project"]["width_um"])
        length_um = float(self.config["project"]["length_um"])
        np.testing.assert_allclose(
            result["Vth_base_normalized_current_A"],
            base_normalized_current,
            rtol=0.0,
            atol=0.0,
        )
        np.testing.assert_allclose(
            result["Vth_normalized_current_A"],
            base_normalized_current * result["Vth_current_multiplier"],
            rtol=1e-14,
            atol=0.0,
        )
        np.testing.assert_allclose(
            result["Vth_target_ID_A"],
            result["Vth_normalized_current_A"] * width_um / length_um,
            rtol=1e-14,
            atol=0.0,
        )

        for _, group in result.groupby(key_columns, sort=False):
            np.testing.assert_allclose(
                group["Vth_current_multiplier"],
                multipliers,
                rtol=0.0,
                atol=0.0,
            )
            ordered = group.sort_values("Vth_current_multiplier")
            self.assertTrue((ordered["Vth_low_V"].diff().dropna() > 0).all())
            self.assertTrue((ordered["Vth_high_V"].diff().dropna() > 0).all())

        base_rows = result[np.isclose(result["Vth_current_multiplier"], 1.0)]
        self.assertEqual(len(base_rows), 3)
        np.testing.assert_allclose(
            base_rows[
                [
                    "Vth_low_shift_mV",
                    "Vth_high_shift_mV",
                    "DIBL_change_mV_per_V",
                ]
            ],
            0.0,
            rtol=0.0,
            atol=1e-12,
        )

    def test_analyze_writes_reproducible_vth_dibl_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch("ptm_pipeline.ROOT", root),
                patch("ptm_pipeline.create_plots"),
                patch("ptm_pipeline.create_vth_dibl_plots"),
                patch("ptm_pipeline.write_comparison_summary"),
            ):
                analyze_data(self.config, self.combined)

            output_path = root / "results" / "vth_dibl_metrics.csv"
            self.assertTrue(output_path.is_file())
            output_bytes = output_path.read_bytes()
            self.assertTrue(output_bytes.endswith(b"\n"))
            self.assertNotIn(b"\r\n", output_bytes)

            written = pd.read_csv(output_path)
            self.assertEqual(list(written.columns), VTH_DIBL_COLUMNS)
            self.assertEqual(len(written), 3)
            np.testing.assert_allclose(
                written["DIBL_mV_per_V"].to_numpy(dtype=float),
                np.array([146.158470072, 76.662051644, 75.953722458]),
                rtol=1e-11,
                atol=1e-9,
            )

            sensitivity_path = root / "results" / "vth_dibl_sensitivity.csv"
            self.assertTrue(sensitivity_path.is_file())
            sensitivity_bytes = sensitivity_path.read_bytes()
            self.assertTrue(sensitivity_bytes.endswith(b"\n"))
            self.assertNotIn(b"\r\n", sensitivity_bytes)

            sensitivity = pd.read_csv(sensitivity_path)
            self.assertEqual(
                list(sensitivity.columns), VTH_DIBL_SENSITIVITY_COLUMNS
            )
            self.assertEqual(
                len(sensitivity),
                3
                * len(
                    self.config["vth_extraction"][
                        "sensitivity_multipliers"
                    ]
                ),
            )


class ModelMetadataTests(unittest.TestCase):
    def test_parses_case_insensitive_model_and_vdd(self) -> None:
        text = """* nominal Vdd = 1.1V
.MODEL NMOS NMOS level=54
"""
        model_name, vdd = parse_model_metadata(text)
        self.assertEqual(model_name, "NMOS")
        self.assertAlmostEqual(vdd, 1.1)

    def test_model_hash_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "models"
            model_dir.mkdir()
            model_path = model_dir / "fixture.pm"
            model_path.write_text(
                "* nominal Vdd = 1.0V\n.MODEL nmos NMOS level=54\n",
                encoding="utf-8",
            )
            entry = {
                "path": "models/fixture.pm",
                "expected_model_name": "nmos",
                "expected_nominal_vdd_v": 1.0,
                "expected_sha256": sha256_file(model_path),
                "official_download_url": "https://example.invalid/model",
            }
            config = {"models": {"HP": entry}}
            self.assertEqual(validate_models(config, root)["HP"].sha256, entry["expected_sha256"])

            model_path.write_text(
                "* nominal Vdd = 1.0V\n.MODEL nmos NMOS level=54\n* changed\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PipelineError, "SHA-256 mismatch"):
                validate_models(config, root)

            malformed = deepcopy(config)
            malformed["models"]["HP"]["expected_sha256"] = "not-a-hash"
            with self.assertRaisesRegex(PipelineError, "64 lowercase"):
                validate_models(malformed, root)


class WrdataParserTests(unittest.TestCase):
    def test_parses_header_and_numeric_rows(self) -> None:
        path = PROJECT_ROOT / "tests" / "fixtures" / "sample_wrdata.txt"
        frame = parse_wrdata(path)
        self.assertEqual(list(frame.columns), ["VGS_V", "ID_A"])
        self.assertEqual(len(frame), 4)
        self.assertAlmostEqual(frame.iloc[-1]["VGS_V"], 0.015)
        self.assertGreater(frame.iloc[-1]["ID_A"], frame.iloc[0]["ID_A"])


class NetlistTests(unittest.TestCase):
    def test_explicit_current_direction_and_dimensions(self) -> None:
        model = ModelInfo(
            application_type="HP",
            path=PROJECT_ROOT / "models" / "45nm_HP.pm",
            model_name="nmos",
            nominal_vdd_v=1.0,
            sha256="0" * 64,
            official_download_url="https://example.invalid/model",
        )
        spec = SweepSpec(
            application_type="HP",
            bias_label="nominal_vdd",
            comparison_basis="model_nominal_vdd",
            vds_v=1.0,
            vgs_start_v=-0.2,
            vgs_stop_v=1.0,
            nominal_vdd_v=1.0,
            model=model,
        )
        config = {
            "project": {
                "width_um": 1.0,
                "length_um": 0.045,
                "temperature_c": 25.0,
                "vgs_start_v": -0.2,
                "vgs_step_v": 0.005,
            }
        }
        text = render_netlist(
            spec, config, PROJECT_ROOT / "data" / "raw" / "raw.txt"
        )
        self.assertIn("M1 drain gate 0 0 nmos W=1u L=0.045u", text)
        self.assertIn("VGS=-0.2..1 V", text)
        self.assertIn("dc VGS -0.2 1 0.005", text)
        self.assertIn("let ID_A = -i(VDS)", text)
        self.assertIn('.include "models/45nm_HP.pm"', text)
        self.assertIn("wrdata data/raw/raw.txt ID_A", text)
        self.assertNotIn('wrdata "', text)
        self.assertNotIn("abs(i(VDS))", text.lower())
        self.assertNotIn(str(PROJECT_ROOT.resolve()), text)


class SweepRangeTests(unittest.TestCase):
    def test_extended_hp_and_lp_row_counts(self) -> None:
        self.assertEqual(expected_row_count(-0.2, 1.0, 0.005), 241)
        self.assertEqual(expected_row_count(-0.2, 1.1, 0.005), 261)

    def test_rejects_invalid_sweep_ranges(self) -> None:
        with self.assertRaisesRegex(PipelineError, "VGS step must be positive"):
            expected_row_count(-0.2, 1.0, 0.0)
        with self.assertRaisesRegex(PipelineError, "VGS stop"):
            expected_row_count(1.0, -0.2, 0.005)
        with self.assertRaisesRegex(PipelineError, "integer multiple"):
            expected_row_count(-0.2, 1.003, 0.005)

    def test_default_inventory_is_five_curves_and_1245_rows(self) -> None:
        config = {
            "project": {
                "low_vds_v": 0.05,
                "include_common_vdd_curve": True,
                "common_vdd_v": 1.0,
                "vgs_start_v": -0.2,
                "vgs_step_v": 0.005,
            }
        }
        models = {
            name: ModelInfo(
                application_type=name,
                path=PROJECT_ROOT / "models" / f"45nm_{name}.pm",
                model_name="nmos",
                nominal_vdd_v=vdd,
                sha256=name * 32,
                official_download_url="https://example.invalid/model",
            )
            for name, vdd in (("HP", 1.0), ("LP", 1.1))
        }
        specs = build_sweep_specs(config, models)
        self.assertEqual(len(specs), 5)
        self.assertTrue(all(spec.vgs_start_v == -0.2 for spec in specs))
        total_rows = sum(
            expected_row_count(spec.vgs_start_v, spec.vgs_stop_v, 0.005)
            for spec in specs
        )
        self.assertEqual(total_rows, 1245)


class SubthresholdSwingTests(unittest.TestCase):
    def test_extracts_known_80_mv_per_decade(self) -> None:
        vgs = np.arange(0.0, 0.601, 0.005)
        ss_v_dec = 0.080
        ioff = 1.0e-12
        ion = 1.0e-3
        current = np.minimum(ioff * np.power(10.0, vgs / ss_v_dec), ion)
        frame = pd.DataFrame({"VGS_V": vgs, "ID_A": current})
        settings = {
            "window_points": 21,
            "min_current_span_decades": 0.75,
            "min_r_squared": 0.995,
            "max_ion_fraction": 0.01,
            "manual_vgs_ranges_v": {},
        }
        result = extract_ss(frame, ion, settings, "TEST.nominal_vdd")
        self.assertAlmostEqual(float(result["SS_mV_dec"]), 80.0, places=6)
        self.assertGreaterEqual(float(result["SS_fit_R_squared"]), 0.999999)


if __name__ == "__main__":
    unittest.main()
