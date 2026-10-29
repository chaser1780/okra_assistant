from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import trading_calendar_status
from helpers import TempAgentHome
from update_trading_calendar import (
    DEFAULT_SSE_URL,
    DEFAULT_SZSE_URL,
    _notice_dates,
    build_calendar_payload,
    maybe_update_calendar,
    parse_official_notice,
    update_calendar,
)


SSE_NOTICE_URL = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml"
SZSE_NOTICE_URL = "https://www.szse.cn/disclosure/notice/general/t20251222_618087.html"

SSE_NOTICE = """<html><body><h1>关于上海证券交易所2026年部分节假日休市安排的通知</h1>
上证公告〔2025〕45号 根据中国证监会有关通知要求，上海证券交易所现将2026年部分节假日休市安排通知如下。
一、休市安排 （一）元旦：1月1日（星期四）至1月3日（星期六）休市，1月5日（星期一）起照常开市。另外，1月4日（星期日）为周末休市。
（二）春节：2月15日（星期日）至2月23日（星期一）休市，2月24日（星期二）起照常开市。另外，2月14日（星期六）、2月28日（星期六）为周末休市。
（三）清明节：4月4日（星期六）至4月6日（星期一）休市，4月7日（星期二）起照常开市。
（四）劳动节：5月1日（星期五）至5月5日（星期二）休市，5月6日（星期三）起照常开市。另外，5月9日（星期六）为周末休市。
（五）端午节：6月19日（星期五）至6月21日（星期日）休市，6月22日（星期一）起照常开市。
（六）中秋节：9月25日（星期五）至9月27日（星期日）休市，9月28日（星期一）起照常开市。
（七）国庆节：10月1日（星期四）至10月7日（星期三）休市，10月8日（星期四）起照常开市。另外，9月20日（星期日）、10月10日（星期六）为周末休市。</body></html>"""
SZSE_NOTICE = SSE_NOTICE.replace(
    "关于上海证券交易所2026年部分节假日休市安排的通知",
    "关于202 6 年部分节假日休市安排的通知",
).replace("现将2026年部分节假日", "现将202 6 年部分节假日")


class FixtureResponse:
    def __init__(self, text: str, status: int = 200):
        self.content = text.encode("utf-8")
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FixtureSession:
    def __init__(self, responses: dict[str, FixtureResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected URL: {url}")
        return self.responses[url]


class TradingCalendarTests(unittest.TestCase):
    def test_parse_official_sse_and_szse_notices_to_matching_full_year_dates(self):
        sse = parse_official_notice(SSE_NOTICE, expected_year=2026)
        szse = parse_official_notice(SZSE_NOTICE, expected_year=2026)
        self.assertEqual(sse, szse)
        self.assertEqual(242, len(sse))
        self.assertNotIn("2026-01-02", sse)
        self.assertIn("2026-01-05", sse)
        self.assertNotIn("2026-10-01", sse)

    def test_parser_keeps_explicit_weekend_makeup_open_day(self):
        text = SSE_NOTICE.replace("1月4日（星期日）为周末休市", "1月4日（星期日）调休开市")
        open_days, makeup_days = _notice_dates(text, 2026)
        self.assertIn("2026-01-04", open_days)
        self.assertEqual({"2026-01-04"}, makeup_days)

    def test_parser_rejects_partial_wrong_year_and_weekday_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, "does not identify"):
            parse_official_notice(SSE_NOTICE, expected_year=2025)
        with self.assertRaisesRegex(RuntimeError, "seven holiday ranges"):
            parse_official_notice(SSE_NOTICE.replace("10月1日（星期四）至10月7日（星期三）休市，10月8日（星期四）起照常开市。", ""), expected_year=2026)
        duplicate_category = SSE_NOTICE.replace("（七）国庆节：", "（七）春节：")
        with self.assertRaisesRegex(RuntimeError, "repeats holiday category"):
            parse_official_notice(duplicate_category, expected_year=2026)
        with self.assertRaisesRegex(RuntimeError, "weekday does not match"):
            parse_official_notice(SSE_NOTICE.replace("1月1日（星期四）", "1月1日（星期五）"), expected_year=2026)

    def test_build_calendar_payload_keeps_weekend_makeup_days(self):
        days = parse_official_notice(SSE_NOTICE, expected_year=2026)
        days.add("2026-01-04")
        payload = build_calendar_payload(2026, days, days, sse_url="sse", szse_url="szse")
        self.assertIn("2026-01-04", payload["makeup_trading_days"])
        self.assertEqual({"sse": "sse", "szse": "szse"}, payload["sources"])
        self.assertTrue(payload["coverage_start"] <= payload["coverage_end"])

    def test_build_calendar_payload_rejects_matching_but_partial_exchange_responses(self):
        with self.assertRaisesRegex(ValueError, "coverage is too small"):
            build_calendar_payload(2026, {"2026-06-01"}, {"2026-06-01"})

    def test_update_calendar_discovers_official_notices_and_records_their_urls(self):
        agent = TempAgentHome()
        try:
            sse_index = f'<a href="{SSE_NOTICE_URL}" title="关于上海证券交易所2026年部分节假日休市安排的通知">公告</a>'
            szse_page = "var cmsParam = { pageCount: 2, }; var curHref = './t20251222_618087.html'; var curTitle ='关于2026年部分节假日休市安排的通知';"
            session = FixtureSession({
                DEFAULT_SSE_URL: FixtureResponse(sse_index),
                SSE_NOTICE_URL: FixtureResponse(SSE_NOTICE),
                DEFAULT_SZSE_URL: FixtureResponse("var cmsParam = { pageCount: 2, };"),
                "https://www.szse.cn/disclosure/notice/general/index_1.html": FixtureResponse(szse_page),
                SZSE_NOTICE_URL: FixtureResponse(SZSE_NOTICE),
            })
            with patch("update_trading_calendar.requests.Session", return_value=session):
                path = update_calendar(agent.root, year=2026)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(SSE_NOTICE_URL, payload["sources"]["sse"])
            self.assertEqual(SZSE_NOTICE_URL, payload["sources"]["szse"])
            self.assertEqual(DEFAULT_SSE_URL, payload["source_indexes"]["sse"])
            self.assertEqual(DEFAULT_SZSE_URL, payload["source_indexes"]["szse"])
            self.assertEqual(5, len(session.calls))
            self.assertEqual("ready", trading_calendar_status(agent.root, "2026-01-02")["reason"])
        finally:
            agent.cleanup()

    def test_html_failure_and_exchange_mismatch_leave_existing_cache_untouched(self):
        agent = TempAgentHome()
        try:
            cache = agent.root / "config" / "trading_calendar.json"
            original = cache.read_text(encoding="utf-8")
            bad_session = FixtureSession({DEFAULT_SSE_URL: FixtureResponse("<html>access denied</html>")})
            with patch("update_trading_calendar.requests.Session", return_value=bad_session):
                with self.assertRaisesRegex(RuntimeError, "no complete official notice"):
                    update_calendar(agent.root, year=2026)
            self.assertEqual(original, cache.read_text(encoding="utf-8"))

            sse_index = f'<a href="{SSE_NOTICE_URL}" title="关于上海证券交易所2026年部分节假日休市安排的通知">公告</a>'
            szse_index = f'<a href="{SZSE_NOTICE_URL}" title="关于2026年部分节假日休市安排的通知">公告</a>'
            different_szse = SZSE_NOTICE.replace("10月7日（星期三）休市", "10月6日（星期二）休市")
            mismatched = FixtureSession({
                DEFAULT_SSE_URL: FixtureResponse(sse_index),
                SSE_NOTICE_URL: FixtureResponse(SSE_NOTICE),
                DEFAULT_SZSE_URL: FixtureResponse(szse_index),
                SZSE_NOTICE_URL: FixtureResponse(different_szse),
            })
            with patch("update_trading_calendar.requests.Session", return_value=mismatched):
                with self.assertRaisesRegex(ValueError, "calendar mismatch"):
                    update_calendar(agent.root, year=2026)
            self.assertEqual(original, cache.read_text(encoding="utf-8"))
        finally:
            agent.cleanup()

    def test_update_failure_preserves_cache_and_daily_attempt_is_deduplicated(self):
        agent = TempAgentHome()
        try:
            original = agent.root / "config" / "trading_calendar.json"
            before = original.read_text(encoding="utf-8")
            calendar_payload = json.loads(before)
            calendar_payload["source_indexes"] = {"sse": "sse", "szse": "szse"}
            original.write_text(json.dumps(calendar_payload), encoding="utf-8")
            before = original.read_text(encoding="utf-8")
            with patch("update_trading_calendar.update_calendar", side_effect=RuntimeError("offline")) as update:
                first = maybe_update_calendar(agent.root, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
                second = maybe_update_calendar(agent.root, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
            self.assertEqual("failed", first["status"])
            self.assertEqual("already_attempted", second["status"])
            self.assertEqual(before, original.read_text(encoding="utf-8"))
            update.assert_called_once()
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
