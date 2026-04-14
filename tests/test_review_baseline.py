from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_advice import compare_against_no_trade, estimated_edge_vs_no_trade


class ReviewBaselineTests(unittest.TestCase):
    def test_add_can_beat_no_trade(self):
        self.assertEqual(compare_against_no_trade("add", 1.5), "better_than_no_trade")
        self.assertEqual(estimated_edge_vs_no_trade("add", 100.0, 1.5), 1.5)

    def test_reduce_can_be_worse_than_no_trade(self):
        self.assertEqual(compare_against_no_trade("reduce", 1.0), "worse_than_no_trade")
        self.assertEqual(estimated_edge_vs_no_trade("reduce", 200.0, 1.0), -2.0)

    def test_hold_matches_no_trade(self):
        self.assertEqual(compare_against_no_trade("hold", -1.2), "same_as_no_trade")
        self.assertEqual(estimated_edge_vs_no_trade("hold", 100.0, -1.2), 0.0)


if __name__ == "__main__":
    unittest.main()
