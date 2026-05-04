from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_fund_news import build_dynamic_sentiment_queries, cookie_has_required_tokens, extract_douyin_aweme_items, extract_xueqiu_status_items, parse_cookie_pairs, read_cookie_file

from helpers import TempAgentHome


class SentimentNewsProviderTests(unittest.TestCase):
    def test_build_dynamic_sentiment_queries_from_holdings(self):
        portfolio = {
            "funds": [
                {"fund_code": "AI1", "fund_name": "天弘中证人工智能C", "role": "tactical", "current_value": 100.0, "style_group": "ai"},
                {"fund_code": "GRID1", "fund_name": "电网设备主题ETF联接C", "role": "tactical", "current_value": 120.0, "style_group": "grid_equipment"},
                {"fund_code": "CASH", "fund_name": "现金仓", "role": "cash_hub", "current_value": 500.0, "style_group": "cash_buffer"},
            ]
        }
        watchlist = {
            "funds": [
                {"code": "AI1", "name": "天弘中证人工智能C", "category": "index_equity", "benchmark": "中证人工智能主题指数"},
                {"code": "GRID1", "name": "电网设备主题ETF联接C", "category": "etf_linked", "benchmark": "中证电网设备主题指数"},
            ]
        }
        settings = {"providers": {"sentiment_news": {"keyword_limit": 12}}}
        queries = build_dynamic_sentiment_queries(portfolio, watchlist, settings)
        keywords = {item["keyword"] for item in queries}
        self.assertIn("AI", keywords)
        self.assertIn("算力", keywords)
        self.assertIn("电网设备", keywords)
        self.assertNotIn("现金仓", keywords)

    def test_read_cookie_file_strips_prefix(self):
        agent = TempAgentHome()
        try:
            agent.write_text("config/xueqiu_cookie.txt", "Cookie: a=1; b=2")
            value = read_cookie_file("config/xueqiu_cookie.txt", agent.root)
            self.assertEqual(value, "a=1; b=2")
        finally:
            agent.cleanup()

    def test_parse_cookie_pairs_and_required_tokens(self):
        cookie_value = "xq_a_token=abc; xq_r_token=def; sessionid=ghi; ttwid=jkl"
        pairs = parse_cookie_pairs(cookie_value)
        self.assertEqual(pairs["xq_a_token"], "abc")
        self.assertTrue(cookie_has_required_tokens("xueqiu", cookie_value))
        self.assertTrue(cookie_has_required_tokens("douyin", cookie_value))

    def test_extract_xueqiu_status_items(self):
        payload = {
            "list": [
                {
                    "id": 123,
                    "text": "<p>AI 算力热度继续抬升</p>",
                    "created_at": 1776393000000,
                    "like_count": 50,
                    "comment_count": 10,
                    "retweet_count": 5,
                    "user": {"id": 999, "screen_name": "tester"},
                }
            ]
        }
        items = extract_xueqiu_status_items(payload)
        self.assertEqual(len(items), 1)
        self.assertIn("AI", items[0]["title"])
        self.assertEqual(items[0]["author_name"], "tester")

    def test_extract_douyin_aweme_items(self):
        payload = {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "123456",
                        "desc": "算力板块今天爆了",
                        "create_time": 1776393000,
                        "author": {"nickname": "douyin-user"},
                        "statistics": {"digg_count": 100, "comment_count": 20, "share_count": 10, "play_count": 10000},
                    }
                }
            ]
        }
        items = extract_douyin_aweme_items(payload)
        self.assertEqual(len(items), 1)
        self.assertIn("算力", items[0]["title"])
        self.assertEqual(items[0]["author_name"], "douyin-user")
        self.assertTrue(items[0]["virality_score"] > 0)


if __name__ == "__main__":
    unittest.main()
