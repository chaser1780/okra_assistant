from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_fund_news import (
    build_dynamic_sentiment_queries,
    classify_news_time,
    classify_news_with_llm,
    compute_heat_metrics,
    cookie_has_required_tokens,
    dedupe_news_items,
    extract_douyin_aweme_items,
    extract_eastmoney_search_items,
    fetch_rss_news,
    extract_xueqiu_status_items,
    fetch_openai_web_search_news,
    filter_news_items_by_report_date,
    normalize_regulatory_item,
    normalize_query_news_item,
    normalize_openai_web_search_item,
    normalize_rss_news_item,
    parse_iso_datetime,
    parse_rss_feed,
    parse_rss_datetime,
    parse_cookie_pairs,
    parse_jsonp_payload,
    parse_sse_general_announcements,
    parse_szse_report_json,
    parse_szse_notice_page,
    fetch_regulatory_news,
    news_dedup_summary,
    read_cookie_file,
    parse_amac_notice_board,
    within_lookback,
)
from news_query_planner import build_news_query_plan, sentiment_queries_from_plan
from multiagent_utils import ProviderRequestError

from helpers import TempAgentHome


def _web_search_response_item() -> dict:
    return {
        "title": "AI compute supply chain update",
        "summary": "A fresh sector update maps to the AI fund.",
        "published_at": "2026-05-10T09:48:52+08:00",
        "source_name": "example finance",
        "url": "https://example.com/ai-update",
        "fund_code": "F1",
        "fund_name": "AI Fund",
        "query_keyword": "AI",
        "query_type": "theme",
        "source_role": "theme_news",
        "source_tier": "financial_media",
        "evidence_type": "theme_news",
        "sentiment_label": "positive",
        "risk_level": "low",
        "risk_tags": [],
        "topic_tags": ["ai"],
        "reason_short": "sector catalyst",
        "relevance_score": 0.82,
    }


class SentimentNewsProviderTests(unittest.TestCase):
    def test_news_classifier_opens_circuit_after_non_retryable_provider_failure(self):
        from unittest.mock import patch

        items = [{"title": f"item-{index}", "summary": "summary"} for index in range(5)]
        settings = {"providers": {"news_classification": {"enabled": True, "batch_size": 2}}}
        failure = ProviderRequestError(
            "model_not_found",
            status_code=404,
            retryable=False,
            request_kind="news_batch_classifier",
            transport_name="direct",
        )

        with patch("fetch_fund_news.call_json_agent", side_effect=failure) as mocked_call:
            classified, summary = classify_news_with_llm(Path.cwd(), settings, items)

        self.assertEqual(mocked_call.call_count, 1)
        self.assertEqual(len(classified), len(items))
        self.assertEqual(summary["fallback_batches"], 3)
        self.assertTrue(summary["circuit_open"])
        self.assertIn("model_not_found", summary["error"])

    def test_news_time_classification_enforces_closed_report_window(self):
        report_date = "2026-07-10"

        self.assertEqual(classify_news_time("2026-07-09T23:59:59+08:00", report_date, 24), "fresh")
        self.assertEqual(classify_news_time("2026-07-10T23:59:59+08:00", report_date, 24), "fresh")
        self.assertEqual(classify_news_time("2026-07-09T23:59:58+08:00", report_date, 24), "stale")
        self.assertEqual(classify_news_time("2026-07-11T00:00:00+08:00", report_date, 24), "future")
        self.assertEqual(classify_news_time("", report_date, 24), "unknown")
        self.assertEqual(classify_news_time("not-a-date", report_date, 24), "unknown")
        self.assertTrue(within_lookback("2026-07-10T23:59:59+08:00", report_date, 24))
        self.assertFalse(within_lookback("2026-07-11T00:00:00+08:00", report_date, 24))

    def test_parse_iso_datetime_normalizes_naive_and_offset_times_to_china(self):
        self.assertEqual(parse_iso_datetime("2026-07-10T09:00:00").isoformat(), "2026-07-10T09:00:00+08:00")
        self.assertEqual(parse_iso_datetime("2026-07-10T01:00:00+00:00").isoformat(), "2026-07-10T09:00:00+08:00")

    def test_final_news_time_gate_drops_future_and_unknown_but_keeps_stale(self):
        items = [
            {"title": "fresh", "published_at": "2026-07-10T09:00:00+08:00"},
            {"title": "stale", "published_at": "2026-06-01T09:00:00+08:00"},
            {"title": "future", "published_at": "2026-07-11T09:00:00+08:00"},
            {"title": "unknown", "published_at": ""},
        ]

        filtered = filter_news_items_by_report_date(items, "2026-07-10")

        self.assertEqual([item["title"] for item in filtered], ["fresh", "stale"])

    def test_news_dedup_summary_counts_final_item_set(self):
        items = [
            {"code": "F1", "title": "same", "summary": "body", "canonical_url": "https://example.test/a", "published_at": "2026-05-15T10:00:00+08:00"},
            {"code": "F2", "title": "same", "summary": "body", "canonical_url": "https://example.test/a", "published_at": "2026-05-15T10:01:00+08:00"},
            {"code": "F1", "title": "same", "summary": "body", "canonical_url": "https://example.test/a", "published_at": "2026-05-15T10:02:00+08:00"},
        ]

        summary = news_dedup_summary(items, dedup_window_hours=12)

        self.assertEqual(summary["mapped_item_count"], 2)
        self.assertEqual(summary["unique_item_count"], 1)
        self.assertEqual(summary["duplicate_item_count"], 1)
        self.assertEqual(summary["dedup_drop_count"], 1)

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

    def test_build_news_query_plan_splits_query_types(self):
        portfolio = {
            "funds": [
                {"fund_code": "AI1", "fund_name": "人工智能C", "role": "tactical", "current_value": 100.0, "style_group": "ai"},
                {"fund_code": "CASH", "fund_name": "现金仓", "role": "cash_hub", "current_value": 500.0, "style_group": "cash_buffer"},
            ]
        }
        watchlist = {
            "funds": [
                {"code": "AI1", "name": "人工智能C", "category": "index_equity", "benchmark": "中证人工智能主题指数"},
            ]
        }
        settings = {"providers": {"news": {"query_limit": 12}, "sentiment_news": {"keyword_limit": 12}}}
        plan = build_news_query_plan(portfolio, watchlist, settings, "2026-05-10")
        self.assertEqual(plan["report_date"], "2026-05-10")
        self.assertTrue(plan["direct_queries"])
        self.assertTrue(plan["theme_queries"])
        self.assertTrue(plan["sentiment_queries"])
        self.assertIn("AI", {item["keyword"] for item in sentiment_queries_from_plan(plan)})

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

    def test_extract_eastmoney_search_items_from_jsonp(self):
        payload = parse_jsonp_payload(
            'callback({"result":{"cmsArticleWebOld":[{"date":"2026-05-10 09:48:52","title":"<em>AI</em>、算力，利好消息","content":"研报称 <em>AI</em> 算力迎来产业加速期","mediaName":"中国证券报","url":"http://finance.eastmoney.com/a/202605103732338111.html","code":"202605103732338111"}]}})'
        )
        items = extract_eastmoney_search_items(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "AI、算力，利好消息")
        self.assertEqual(items[0]["source_name"], "中国证券报")

    def test_normalize_query_news_item_maps_to_related_funds(self):
        raw_item = {
            "title": "AI、算力，利好消息",
            "summary": "AI 算力迎来产业加速期",
            "published_at": "2026-05-10T09:48:52+08:00",
            "source_name": "中国证券报",
            "url": "http://finance.eastmoney.com/a/202605103732338111.html",
        }
        query = {"keyword": "AI", "fund_codes": ["F1", "F2"], "fund_names": ["人工智能C", "科技成长C"]}
        items = normalize_query_news_item(raw_item, query, source_role="theme_news", report_date="2026-05-10")
        self.assertEqual({item["code"] for item in items}, {"F1", "F2"})
        self.assertTrue(all(item["provider"] == "eastmoney_search_api" for item in items))
        self.assertTrue(all(item["evidence_type"] == "theme_news" for item in items))

    def test_normalize_query_news_item_rejects_future_and_unknown_times(self):
        query = {"keyword": "AI", "fund_codes": ["F1"], "fund_names": ["AI Fund"]}
        base_item = {"title": "AI update", "summary": "update", "url": "https://example.com/ai"}

        self.assertEqual(
            normalize_query_news_item({**base_item, "published_at": "2026-07-11T00:00:00+08:00"}, query, source_role="theme_news", report_date="2026-07-10"),
            [],
        )
        self.assertEqual(
            normalize_query_news_item({**base_item, "published_at": "invalid"}, query, source_role="theme_news", report_date="2026-07-10"),
            [],
        )

    def test_dedupe_and_heat_metrics_preserve_multi_fund_mapping(self):
        items = [
            {
                "code": "F1",
                "title": "AI 算力继续升温",
                "summary": "AI 算力继续升温",
                "published_at": "2026-05-10T09:48:52+08:00",
                "url": "http://finance.eastmoney.com/a/202605103732338111.html?spm=abc",
                "source_name": "中国证券报",
                "matched_keywords": ["AI"],
                "query_type": "direct",
            },
            {
                "code": "F2",
                "title": "AI 算力继续升温",
                "summary": "AI 算力继续升温",
                "published_at": "2026-05-10T09:48:52+08:00",
                "url": "http://finance.eastmoney.com/a/202605103732338111.html?spm=def",
                "source_name": "中国证券报",
                "matched_keywords": ["AI"],
                "query_type": "direct",
            },
            {
                "code": "F1",
                "title": "AI 算力继续升温",
                "summary": "AI 算力继续升温",
                "published_at": "2026-05-10T09:48:52+08:00",
                "url": "http://finance.eastmoney.com/a/202605103732338111.html?spm=ghi",
                "source_name": "中国证券报",
                "matched_keywords": ["AI"],
                "query_type": "direct",
            },
        ]
        deduped, stats = dedupe_news_items(items, dedup_window_hours=12)
        compute_heat_metrics(deduped)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(stats["mapped_item_count"], 2)
        self.assertEqual(stats["unique_item_count"], 1)
        self.assertGreaterEqual(float(deduped[0]["heat_score"]), 0.0)
        self.assertTrue(all(int(item["heat_rank"]) >= 1 for item in deduped))

    def test_classify_news_with_llm_falls_back_to_rule(self):
        agent = TempAgentHome()
        try:
            settings = {
                "providers": {
                    "news_classification": {
                        "enabled": True,
                        "mode": "llm_first",
                        "batch_size": 20,
                        "timeout_seconds": 1,
                        "fallback": "rule",
                        "model": "",
                    }
                }
            }
            items = [
                {
                    "title": "基金清盘风险提示公告",
                    "summary": "出现清盘风险提示",
                    "source_name": "eastmoney_notice",
                    "source_role": "fund_news",
                    "published_at": "2026-05-10T09:48:52+08:00",
                    "matched_keywords": ["清盘"],
                }
            ]
            classified, summary = classify_news_with_llm(agent.root, settings, items)
            self.assertEqual(summary["status"], "fallback_only")
            self.assertEqual(classified[0]["classification_status"], "rule_fallback")
            self.assertEqual(classified[0]["risk_level"], "high")
            self.assertEqual(classified[0]["impact"], "negative")
        finally:
            agent.cleanup()

    def test_parse_rss_feed_and_fetch_rss_news(self):
        self.assertEqual(parse_rss_datetime("Thu, 14 May 2026 22:26:52 +0800", "2026-05-15"), "2026-05-14T22:26:52+08:00")

        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Finance Feed</title>
            <item>
              <title>AI 算力迎来产业加速期</title>
              <description>AI 算力板块继续升温</description>
              <link>https://example.com/rss/ai-1</link>
              <pubDate>Sat, 10 May 2026 09:48:52 +0800</pubDate>
            </item>
          </channel>
        </rss>
        """
        rows = parse_rss_feed(xml_text, "2026-05-10")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "AI 算力迎来产业加速期")

        agent = TempAgentHome()
        try:
            settings = {
                "providers": {
                    "rss_news": {
                        "enabled": True,
                        "timeout_seconds": 12,
                        "feeds": [{"name": "sina_finance", "url": "https://example.com/rss.xml", "provider": "rss:sina_finance"}],
                    }
                }
            }
            query_plan = {
                "direct_queries": [{"keyword": "AI", "fund_codes": ["F1"], "fund_names": ["人工智能C"], "query_type": "direct"}],
                "theme_queries": [],
                "market_queries": [],
            }
            from unittest.mock import patch

            with patch("fetch_fund_news.fetch_xml_text", return_value=xml_text):
                items, health = fetch_rss_news(settings, "2026-05-10", query_plan)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["provider"], "rss:sina_finance")
            self.assertEqual(items[0]["source_role"], "fund_news")
            self.assertEqual(items[0]["query_type"], "direct")
            self.assertEqual(health[0]["metrics"]["raw_item_count"], 1)
            self.assertEqual(health[0]["metrics"]["matched_item_count"], 1)
        finally:
            agent.cleanup()

    def test_normalize_rss_news_item_rejects_future_and_unknown_times(self):
        query = {"keyword": "AI", "fund_codes": ["F1"], "fund_names": ["AI Fund"], "query_type": "direct"}
        base_item = {"title": "AI update", "summary": "update", "url": "https://example.com/rss/ai"}

        self.assertEqual(
            normalize_rss_news_item(
                {**base_item, "published_at": "2026-07-11T00:00:00+08:00"},
                query,
                feed_name="finance_feed",
                provider_name="rss:finance",
                report_date="2026-07-10",
            ),
            [],
        )
        self.assertEqual(
            normalize_rss_news_item(
                {**base_item, "published_at": ""},
                query,
                feed_name="finance_feed",
                provider_name="rss:finance",
                report_date="2026-07-10",
            ),
            [],
        )

    def test_normalize_regulatory_item_rejects_future_and_unknown_times(self):
        base_item = {"title": "监管公告", "summary": "notice", "url": "https://example.com/regulatory"}

        self.assertIsNone(
            normalize_regulatory_item(
                {**base_item, "published_at": "2026-07-11T00:00:00+08:00"},
                provider_name="reg:test",
                feed_name="test regulator",
                report_date="2026-07-10",
            )
        )
        self.assertIsNone(
            normalize_regulatory_item(
                {**base_item, "published_at": "invalid"},
                provider_name="reg:test",
                feed_name="test regulator",
                report_date="2026-07-10",
            )
        )

    def test_fetch_news_demo_with_rss_disabled_still_writes_new_fields(self):
        agent = TempAgentHome()
        try:
            agent.run_script("fetch_fund_news.py", "--date", "2026-05-14", "--demo")
            payload = json.loads((agent.root / "raw" / "news" / "2026-05-14.json").read_text(encoding="utf-8"))
            self.assertIn("dedup_summary", payload)
            self.assertIn("classification_summary", payload)
            self.assertIn("query_plan", payload)
            self.assertTrue(any(item.get("source_key") == "sentiment:xueqiu_web" and item.get("status") == "disabled" for item in payload.get("source_health", [])))
        finally:
            agent.cleanup()

    def test_parse_sse_general_announcements_and_fetch_regulatory_news(self):
        html = """
        <html><body>
        <a href="/disclosure/announcement/general/c/c_20260515_10899999.shtml" title="关于某基金临时停牌的公告">关于某基金临时停牌的公告</a>
        <a href="/disclosure/announcement/general/jjzssgg/c/c_20260515_10899998.shtml" title="关于某ETF提供做市服务的公告">关于某ETF提供做市服务的公告</a>
        </body></html>
        """
        rows = parse_sse_general_announcements(html, "https://www.sse.com.cn/disclosure/announcement/general/", "2026-05-15")
        self.assertEqual(len(rows), 2)
        self.assertIn("临时停牌", rows[0]["title"])

        from unittest.mock import patch

        settings = {
            "providers": {
                "regulatory_news": {
                    "enabled": True,
                    "timeout_seconds": 15,
                    "feeds": [
                        {
                            "name": "sse_general_announcements",
                            "url": "https://www.sse.com.cn/disclosure/announcement/general/",
                            "provider": "reg:sse_general",
                            "source_role": "regulatory_news",
                        }
                    ],
                }
            }
        }
        with patch("fetch_fund_news.fetch_xml_text", return_value=html):
            items, health = fetch_regulatory_news(settings, "2026-05-15")
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["source_role"] == "regulatory_news" for item in items))
        self.assertTrue(all(item["evidence_type"] == "regulatory_notice" for item in items))
        self.assertEqual(health[0]["metrics"]["normalized_count"], 2)

    def test_parse_szse_notice_page_and_fetch_regulatory_news(self):
        html = """
        <html><body>
        <a href="/disclosure/listed/notice/2026-05-15/notice-1.html" title="关于上市公司重大事项公告">关于上市公司重大事项公告</a>
        <a href="/disclosure/supervision/inquire/2026-05-15/inquire-1.html">关于某公司年报问询函</a>
        <a href="/market/index.html">无关链接</a>
        </body></html>
        """
        rows = parse_szse_notice_page(html, "https://www.szse.cn/disclosure/listed/notice/index.html", "2026-05-15")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["published_at"], "2026-05-15T00:00:00+08:00")
        self.assertTrue(all(row["url"].startswith("https://www.szse.cn/") for row in rows))

        from unittest.mock import patch

        settings = {
            "providers": {
                "regulatory_news": {
                    "enabled": True,
                    "timeout_seconds": 15,
                    "feeds": [
                        {
                            "name": "szse_listed_notices",
                            "url": "https://www.szse.cn/disclosure/listed/notice/index.html",
                            "provider": "reg:szse_listed_notice",
                            "source_role": "regulatory_news",
                        }
                    ],
                }
            }
        }
        with patch("fetch_fund_news.fetch_xml_text", return_value=html):
            items, health = fetch_regulatory_news(settings, "2026-05-15")
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["provider"] == "reg:szse_listed_notice" for item in items))
        self.assertTrue(all(item["source_role"] == "regulatory_news" for item in items))
        self.assertEqual(health[0]["metrics"]["normalized_count"], 2)

    def test_parse_szse_report_json_for_official_inquiry_api(self):
        payload = json.dumps(
            [
                {
                    "metadata": {"catalogid": "main_wxhj", "name": "主板"},
                    "data": [
                        {
                            "gsdm": "000711",
                            "gsjc": "ST京蓝",
                            "fhrq": "2026-05-13",
                            "hjlb": "关注函",
                            "ck": "<a href='javascript:void(0)' encode-open='/UpFiles/zqjghj/sup_jghj_test.pdf'>详细内容</a>",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        )
        rows = parse_szse_report_json(payload, "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=main_wxhj", "2026-05-15")
        self.assertEqual(len(rows), 1)
        self.assertIn("ST京蓝", rows[0]["title"])
        self.assertEqual(rows[0]["published_at"], "2026-05-13T00:00:00+08:00")
        self.assertTrue(rows[0]["url"].startswith("https://www.szse.cn/UpFiles/"))

        from unittest.mock import patch

        settings = {
            "providers": {
                "regulatory_news": {
                    "enabled": True,
                    "timeout_seconds": 15,
                    "feeds": [
                        {
                            "name": "szse_inquiries",
                            "url": "https://www.szse.cn/disclosure/supervision/inquire/index.html",
                            "provider": "reg:szse_inquiry",
                            "source_role": "regulatory_news",
                        }
                    ],
                }
            }
        }
        with patch("fetch_fund_news.fetch_json_text", return_value=payload):
            items, health = fetch_regulatory_news(settings, "2026-05-15")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["provider"], "reg:szse_inquiry")
        self.assertEqual(health[0]["metrics"]["normalized_count"], 1)

    def test_parse_amac_notice_board_filters_only_regulatory_items(self):
        html = """
        <html><body>
        <a href="../../zlgl/jlcf/scfjg/202605/P020260508595084826608.pdf">纪律处分决定书（某私募机构）</a>
        <a href="../../zlgl/ycjy/ycjyjgclgg/202605/t20260508_27685.html">关于注销某异常经营私募基金管理人登记的公告</a>
        <a href="../xhyw/202604/t20260417_27594.html">关于发布《基金管理公司绩效考核管理指引》的公告</a>
        </body></html>
        """
        rows = parse_amac_notice_board(html, "https://www.amac.org.cn/xwfb/tzgg/", "2026-05-15")
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("纪律处分决定书" in row["title"] for row in rows))
        self.assertTrue(any("异常经营" in row["title"] for row in rows))

    def test_normalize_openai_web_search_item_maps_to_existing_news_shape(self):
        item = normalize_openai_web_search_item(_web_search_response_item(), report_date="2026-05-10")

        self.assertIsNotNone(item)
        self.assertEqual(item["provider"], "openai_web_search")
        self.assertEqual(item["code"], "F1")
        self.assertEqual(item["source_role"], "theme_news")
        self.assertEqual(item["evidence_type"], "theme_news")
        self.assertEqual(item["matched_keywords"], ["AI"])

    def test_normalize_openai_web_search_item_rejects_future_and_unknown_times(self):
        future = {**_web_search_response_item(), "published_at": "2026-05-11T00:00:00+08:00"}
        unknown = {**_web_search_response_item(), "published_at": "invalid"}

        self.assertIsNone(normalize_openai_web_search_item(future, report_date="2026-05-10"))
        self.assertIsNone(normalize_openai_web_search_item(unknown, report_date="2026-05-10"))

    def test_news_filter_rejects_same_day_item_after_decision_cutoff(self):
        items = [
            {"published_at": "2026-05-10T21:00:00+08:00", "title": "before"},
            {"published_at": "2026-05-10T22:00:00+08:00", "title": "after"},
        ]

        filtered = filter_news_items_by_report_date(
            items,
            "2026-05-10",
            "2026-05-10T21:30:00+08:00",
        )

        self.assertEqual(["before"], [item["title"] for item in filtered])

    def test_fetch_openai_web_search_news_uses_responses_tool_and_normalizes_items(self):
        agent = TempAgentHome()
        try:
            settings = {
                "providers": {
                    "openai_web_search_news": {
                        "enabled": True,
                        "timeout_seconds": 30,
                        "max_attempts": 1,
                        "max_queries": 2,
                        "max_queries_per_bucket": 1,
                        "results_per_query": 1,
                        "freshness_days": 7,
                        "dedup_window_hours": 12,
                        "tool_types": ["web_search"],
                    }
                }
            }
            query_plan = {
                "direct_queries": [{"keyword": "F1", "fund_codes": ["F1"], "fund_names": ["AI Fund"], "query_type": "direct"}],
                "theme_queries": [{"keyword": "AI", "fund_codes": ["F1"], "fund_names": ["AI Fund"], "query_type": "theme"}],
                "market_queries": [],
            }
            response_json = {"items": [_web_search_response_item()]}

            from unittest.mock import patch

            response = {
                "output_text": json.dumps(response_json),
                "completed_event": {
                    "type": "response.completed",
                    "response": {
                        "output": [
                            {
                                "content": [
                                    {
                                        "type": "output_text",
                                        "annotations": [{"type": "url_citation", "url": "https://example.com/ai-update"}],
                                    }
                                ]
                            }
                        ]
                    },
                },
            }
            with patch("fetch_fund_news.call_responses_text", return_value=response) as mock_call:
                items, health = fetch_openai_web_search_news(agent.root, settings, "2026-05-10", query_plan)

            payload = mock_call.call_args.args[1]
            self.assertEqual(payload["tools"][0]["type"], "web_search")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["provider"], "openai_web_search")
            self.assertEqual(items[0]["code"], "F1")
            self.assertTrue(items[0]["citation_verified"])
            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["metrics"]["selected_tool"], "web_search")
            self.assertEqual(health["metrics"]["citation_url_count"], 1)
        finally:
            agent.cleanup()

    def test_fetch_openai_web_search_rejects_uncited_model_url(self):
        agent = TempAgentHome()
        try:
            settings = {"providers": {"openai_web_search_news": {"enabled": True, "tool_types": ["web_search"]}}}
            query_plan = {
                "direct_queries": [{"keyword": "F1", "fund_codes": ["F1"]}],
                "theme_queries": [],
                "market_queries": [],
            }
            from unittest.mock import patch

            with patch(
                "fetch_fund_news.call_responses_text",
                return_value={"output_text": json.dumps({"items": [_web_search_response_item()]})},
            ):
                items, health = fetch_openai_web_search_news(agent.root, settings, "2026-05-10", query_plan)

            self.assertEqual([], items)
            self.assertEqual("warning", health["status"])
            self.assertEqual(1, health["metrics"]["unverified_item_count"])
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
