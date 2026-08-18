from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ptm_pipeline import (  # noqa: E402
    ModelInfo,
    PipelineError,
    SweepSpec,
    build_sweep_specs,
    expected_row_count,
    extract_ss,
    parse_model_metadata,
    parse_wrdata,
    render_netlist,
    sha256_file,
    validate_models,
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
