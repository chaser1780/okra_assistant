from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_advice import build_review_items

FUND_NAV = [{"date": "2026-05-20", "nav": 1.0}, {"date": "2026-05-28", "nav": 1.08}]  # +8%
BENCH_NAV = [{"date": "2026-05-20", "nav": 100.0}, {"date": "2026-05-28", "nav": 102.0}]  # +2%


def _build(benchmark_history):
    return build_review_items(
        source="advice",
        source_items=[{"fund_code": "F1", "fund_name": "F1", "action": "add", "amount": 1000, "suggestion_id": "s1", "agent_support": []}],
        quotes={"F1": {"day_change_pct": 1.5}},
        estimates={},
        proxies={"F1": {"change_pct": 0.5}},  # base 日 proxy 日涨跌，不得当区间基准
        watchlist={"F1": {"benchmark": "bench"}},
        constraint_map={"F1": {}},
        nav_history_by_code={"F1": FUND_NAV},
        base_date="2026-05-20",
        review_date="2026-05-28",
        horizon=8,
        benchmark_history_by_code=benchmark_history,
    )[0]


class ReviewExcessGapTests(unittest.TestCase):
    def test_excess_uses_same_window_fund_and_benchmark_nav(self):
        row = _build({"F1": BENCH_NAV})[0]
        self.assertEqual(row["benchmark_period_return_pct"], 2.0)
        # 同区间基金 8% - 同区间 benchmark 2% = 6%
        self.assertEqual(row["excess_return_vs_benchmark_pct"], 6.0)
        self.assertFalse(row["benchmark_signal_gap"])

    def test_fund_period_return_but_no_benchmark_nav_gap(self):
        # 反例：基金 period_return 存在，但 benchmark 区间 NAV 缺失 -> excess 必须 None，
        # 不能用 base 日 proxy change(0.5%) 冒充基准
        row = _build({})[0]
        self.assertEqual(row["evaluation_basis"], "period_return")
        self.assertIsNone(row["benchmark_period_return_pct"])
        self.assertIsNone(row["excess_return_vs_benchmark_pct"])
        self.assertTrue(row["benchmark_signal_gap"])

    def test_mismatched_window_dates_are_gap(self):
        # 反例：benchmark 最近取值落在 05-19/05-27，与基金 05-20/05-28 区间日期不一致，
        # 不各自最近拼误差 -> excess 必须 None
        row = _build({"F1": [{"date": "2026-05-19", "nav": 100.0}, {"date": "2026-05-27", "nav": 102.0}]})[0]
        self.assertIsNone(row["excess_return_vs_benchmark_pct"])
        self.assertTrue(row["benchmark_signal_gap"])


if __name__ == "__main__":
    unittest.main()
