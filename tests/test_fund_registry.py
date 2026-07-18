from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fund_registry import extract_eastmoney_fund_candidates, lookup_fund_by_code, search_fund_candidates


def provider_payload(code: str = "012348", name: str = "天弘恒生科技ETF联接A") -> dict:
    return {
        "Datas": [
            {
                "CODE": code,
                "NAME": name,
                "CATEGORY": 700,
                "FundBaseInfo": {
                    "SHORTNAME": name,
                    "OTHERNAME": "天弘恒生科技指数(QDII)A,天弘恒生科技A",
                    "FTYPE": "指数型-海外股票",
                    "JJGS": "天弘基金",
                    "JJJL": "胡超",
                    "DWJZ": 0.6466,
                    "FSRQ": "2026-07-10",
                },
            },
            {"CODE": "300061", "NAME": "旗天科技", "CATEGORY": 150, "FundBaseInfo": None},
        ]
    }


class FundRegistryTests(unittest.TestCase):
    def test_extract_candidates_keeps_only_funds_and_exposes_identity_evidence(self):
        items = extract_eastmoney_fund_candidates(provider_payload(), "天弘恒生科技ETF联接(QDII)A")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["fund_code"], "012348")
        self.assertEqual(items[0]["category"], "etf_linked")
        self.assertEqual(items[0]["company_name"], "天弘基金")
        self.assertGreaterEqual(items[0]["match_score"], 0.85)
        self.assertIn("012348", items[0]["source_url"])

    def test_search_retries_with_shorter_name_variant(self):
        with patch("fund_registry._request_search_payload", side_effect=[{"Datas": []}, provider_payload()]) as request:
            result = search_fund_candidates("天弘恒生科技ETF联接(QDII)A")

        self.assertEqual(result["candidates"][0]["fund_code"], "012348")
        self.assertEqual(request.call_count, 2)

    def test_lookup_by_code_rejects_non_fund_results(self):
        with patch("fund_registry._request_search_payload", return_value=provider_payload()):
            self.assertEqual(lookup_fund_by_code("012348")["fund_name"], "天弘恒生科技ETF联接A")
        with self.assertRaisesRegex(ValueError, "6 digits"):
            lookup_fund_by_code("ABC")


if __name__ == "__main__":
    unittest.main()
