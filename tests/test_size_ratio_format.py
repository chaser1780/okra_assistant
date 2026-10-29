from __future__ import annotations
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from web_api_format import adapt_simulation_advice_row


class SizeRatioFormatTests(unittest.TestCase):
    def test_valid_ratio_preserved(self):
        row = {"schema_version": "simulation_v2", "size_ratio": 0.9, "size_tier": "large"}
        self.assertEqual(adapt_simulation_advice_row(row)["sizeRatio"], 0.9)

    def test_zero_ratio_kept_not_missing(self):
        row = {"schema_version": "simulation_v2", "size_ratio": 0.0, "size_tier": "small"}
        self.assertEqual(adapt_simulation_advice_row(row)["sizeRatio"], 0.0)

    def test_nan_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": float("nan"), "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_inf_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": float("inf"), "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_negative_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": -0.5, "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_gt_one_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": 2.5, "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_numeric_string_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": "0.5", "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_missing_ratio_legacy_none(self):
        row = {"schema_version": "simulation_v2", "size_tier": "large"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_invalid_tier_closed_to_none_ratio_null(self):
        row = {"schema_version": "simulation_v2", "size_ratio": 0.9, "size_tier": "huge"}
        out = adapt_simulation_advice_row(row)
        self.assertEqual(out["sizeTier"], "none")
        self.assertIsNone(out["sizeRatio"])

    def test_bool_rejected(self):
        row = {"schema_version": "simulation_v2", "size_ratio": True, "size_tier": "small"}
        self.assertIsNone(adapt_simulation_advice_row(row)["sizeRatio"])

    def test_long_float_ratio_preserved_unrounded(self):
        row = {"schema_version": "simulation_v2", "size_ratio": 0.123456789, "size_tier": "small"}
        self.assertEqual(adapt_simulation_advice_row(row)["sizeRatio"], 0.123456789)


if __name__ == "__main__":
    unittest.main()
