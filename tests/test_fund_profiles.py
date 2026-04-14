from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_fund_profiles import parse_profile_html


class FundProfileTests(unittest.TestCase):
    def test_parse_profile_html_extracts_core_fields(self):
        html = """
        <html><body>
        <div>
        成立日期：2023-05-30
        基金经理：贺雨轩
        类型：指数型-股票
        管理人：天弘基金
        基金规模：12.34亿元
        管理费率：0.50%
        托管费率：0.10%
        </div>
        </body></html>
        """
        profile = parse_profile_html(html, "017193", "测试基金", "2026-03-11")
        self.assertEqual(profile["fund_code"], "017193")
        self.assertEqual(profile["inception_date"], "2023-05-30")
        self.assertEqual(profile["fund_manager"], "贺雨轩")
        self.assertEqual(profile["fund_type"], "指数型-股票")
        self.assertEqual(profile["management_company"], "天弘基金")
        self.assertEqual(profile["fund_scale_billion"], 12.34)
        self.assertEqual(profile["management_fee_rate"], 0.5)
        self.assertEqual(profile["custody_fee_rate"], 0.1)
        self.assertGreater(profile["fund_age_years"], 2.0)
        self.assertEqual(profile["fund_scale_bucket"], "medium")
        self.assertEqual(profile["fee_level"], "medium")


if __name__ == "__main__":
    unittest.main()
