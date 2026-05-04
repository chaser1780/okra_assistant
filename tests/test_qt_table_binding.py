from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qtui.widgets import FilterableTablePage


class QtTableBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_detail_binding_tracks_sorted_row_key(self):
        page = FilterableTablePage("测试", ["代码", "值"], show_summary=False, show_detail=True)
        page.configure(
            detail_builder=lambda row: f"detail:{row['fund_code']}",
            cells_builder=lambda row: [row["fund_code"], row["value"]],
            row_key_builder=lambda row: row["fund_code"],
        )
        page.load_rows(
            "meta",
            [
                {"fund_code": "A", "value": 10},
                {"fund_code": "B", "value": 30},
                {"fund_code": "C", "value": 20},
            ],
        )
        page.table.sortByColumn(1, Qt.DescendingOrder)
        self.app.processEvents()
        page.table.selectRow(0)
        self.app.processEvents()

        row = page.current_row()
        self.assertIsNotNone(row)
        self.assertEqual(row["fund_code"], "B")
        self.assertEqual(page.detail.toPlainText(), "detail:B")


if __name__ == "__main__":
    unittest.main()
