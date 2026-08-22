from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from workbench_history import (  # noqa: E402
    SeriesPoint,
    allocation_history,
    cap_points,
    daily_return_series,
    drawdown_series,
    normalized_series,
)


class WorkbenchHistoryTests(unittest.TestCase):
    def test_normalized_daily_return_and_drawdown(self):
        points = [SeriesPoint("2026-01-01", 100.0), SeriesPoint("2026-01-02", 110.0), SeriesPoint("2026-01-03", 99.0)]
        self.assertEqual([point.value for point in normalized_series(points)], [100.0, 110.0, 99.0])
        self.assertEqual([point.value for point in daily_return_series(points)], [0.0, 10.0, -10.0])
        self.assertEqual([point.value for point in drawdown_series(points)], [0.0, 0.0, -10.0])

    def test_allocation_history_is_date_limited_and_weighted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = root / "db" / "portfolio_state" / "snapshots"
            snapshot_dir.mkdir(parents=True)
            for date, first, second in (("2026-01-01", 75, 25), ("2026-01-02", 60, 40), ("2026-01-03", 50, 50)):
                (snapshot_dir / f"{date}.json").write_text(
                    json.dumps({
                        "total_value": 1000,
                        "funds": [
                            {"fund_code": "A", "current_value": first, "style_group": "core"},
                            {"fund_code": "B", "current_value": second, "style_group": "satellite"},
                        ],
                    }),
                    encoding="utf-8",
                )
            history = allocation_history(root, "style_group", end_date="2026-01-02")
            self.assertEqual([row["date"] for row in history], ["2026-01-01", "2026-01-02"])
            self.assertEqual(history[-1]["values"][0], {"name": "core", "weight": 6.0})

    def test_cap_points_blocks_future_history(self):
        points = [SeriesPoint("2026-05-20", 100), SeriesPoint("2026-05-21", 110)]
        self.assertEqual(cap_points(points, "2026-05-20"), [points[0]])


if __name__ == "__main__":
    unittest.main()
