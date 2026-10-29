"""Equivalence tests for the run_task skip-envelope refactor.

These tests pin the *behavior* of the six automatic skip branches in
``TaskController.run_task`` after extracting the shared envelope into
``_task_skip_payload``. They compare against the pre-refactor literal shape
(exact key order, literal field values, calendar object identity, call order,
fresh per-call dict objects, None/missing reason semantics) and mock every
boundary so no subprocess spawns, no network is touched and no runtime database
under the real agent home is read or written.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import web_api_services as services  # noqa: E402
from today_orchestrator import AlreadyRunningError  # noqa: E402

FIXED_TODAY = "2026-10-28"
HISTORICAL_DATE = "2026-10-20"

EXPECTED_KEYS = [
    "ok",
    "task",
    "pid",
    "runId",
    "runDate",
    "force",
    "logPath",
    "portfolioAlignment",
    "alreadyRunning",
    "skipped",
    "reason",
    "calendar",
]


class SkipPayloadEquivalenceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.controller = services.TaskController(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_skip_case(self, kind, calendar, *, trading_day, window, calls, run_date=None, force=True):
        """Execute an automatic run_task that must hit a skip branch, recording call order.

        today_str is frozen to a constant so realtime runDate assertions never
        touch the wall clock (no midnight flakiness).
        """
        fake_calendar = dict(calendar)

        def fake_automatic_calendar(_self, _date):
            calls.append("automatic_calendar")
            return fake_calendar

        def fake_is_trading_day(_home, _date):
            calls.append("is_trading_day")
            return trading_day

        def fake_window(_self):
            calls.append("realtime_window")
            return window

        with (
            mock.patch.object(services.TaskController, "_automatic_calendar", fake_automatic_calendar),
            mock.patch.object(services, "is_trading_day", fake_is_trading_day),
            mock.patch.object(services.TaskController, "_automatic_realtime_window", fake_window),
            mock.patch.object(services, "today_str", lambda: FIXED_TODAY),
        ):
            result = self.controller.run_task(kind, force=force, run_date=run_date, automatic=True)
        return result, fake_calendar

    def _assert_skip_shape(self, result, *, task, reason, run_date, fake_calendar):
        self.assertEqual(list(result.keys()), EXPECTED_KEYS)
        self.assertIs(result["calendar"], fake_calendar)  # calendar object identity preserved
        self.assertIsNot(result["portfolioAlignment"], {})  # fresh dict, not the module constant
        self.assertEqual(
            {
                "ok": result["ok"],
                "pid": result["pid"],
                "runId": result["runId"],
                "logPath": result["logPath"],
                "alreadyRunning": result["alreadyRunning"],
                "skipped": result["skipped"],
            },
            {
                "ok": True,
                "pid": 0,
                "runId": "",
                "logPath": "",
                "alreadyRunning": False,
                "skipped": True,
            },
        )
        self.assertEqual(result["task"], task)
        self.assertEqual(result["reason"], reason)
        self.assertEqual(result["runDate"], run_date)
        self.assertIs(result["force"], False)  # caller force=True must NOT leak into the skip payload
        self.assertEqual(result["portfolioAlignment"], {})

    def test_daily_calendar_not_ready_ignores_force(self):
        calls = []
        calendar = {"ready": False, "reason": "calendar_refresh_failed"}
        result, fake = self._run_skip_case(
            "daily", calendar, trading_day=True, window="session", calls=calls, run_date=HISTORICAL_DATE
        )
        # explicit historical date passes through verbatim
        self._assert_skip_shape(result, task="daily", reason="calendar_refresh_failed", run_date=HISTORICAL_DATE, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar"])  # non-trading-day gate must not run after not-ready

    def test_daily_calendar_not_ready_missing_reason_uses_default(self):
        calls = []
        calendar = {"ready": False}  # no "reason" key at all
        result, fake = self._run_skip_case(
            "daily", calendar, trading_day=True, window="session", calls=calls, run_date=HISTORICAL_DATE
        )
        self._assert_skip_shape(result, task="daily", reason="trading_calendar_not_ready", run_date=HISTORICAL_DATE, fake_calendar=fake)

    def test_daily_calendar_not_ready_none_reason_stays_none(self):
        # dict.get(key, default) returns None when the key exists with value None;
        # the refactor must preserve that quirk byte-for-byte.
        calls = []
        calendar = {"ready": False, "reason": None}
        result, fake = self._run_skip_case(
            "daily", calendar, trading_day=True, window="session", calls=calls, run_date=HISTORICAL_DATE
        )
        self._assert_skip_shape(result, task="daily", reason=None, run_date=HISTORICAL_DATE, fake_calendar=fake)

    def test_daily_non_trading_day_reason(self):
        calls = []
        calendar = {"ready": True, "trading": True}
        result, fake = self._run_skip_case(
            "daily", calendar, trading_day=False, window="session", calls=calls, run_date=HISTORICAL_DATE
        )
        self._assert_skip_shape(result, task="daily", reason="non_trading_day", run_date=HISTORICAL_DATE, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar", "is_trading_day"])  # order preserved

    def test_realtime_calendar_not_ready(self):
        calls = []
        calendar = {"ready": False, "reason": "trading_calendar_not_ready"}
        result, fake = self._run_skip_case(
            "realtime", calendar, trading_day=True, window="session", calls=calls
        )
        # realtime forces run_date to the frozen today even though the caller may pass one
        self._assert_skip_shape(result, task="realtime", reason="trading_calendar_not_ready", run_date=FIXED_TODAY, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar"])

    def test_realtime_non_trading_day(self):
        calls = []
        calendar = {"ready": True}
        result, fake = self._run_skip_case(
            "realtime", calendar, trading_day=False, window="session", calls=calls
        )
        self._assert_skip_shape(result, task="realtime", reason="non_trading_day", run_date=FIXED_TODAY, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar", "is_trading_day"])

    def test_realtime_outside_session(self):
        calls = []
        calendar = {"ready": True}
        result, fake = self._run_skip_case(
            "realtime", calendar, trading_day=True, window="outside", calls=calls
        )
        self._assert_skip_shape(result, task="realtime", reason="outside_trading_session", run_date=FIXED_TODAY, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar", "is_trading_day", "realtime_window"])

    def test_realtime_after_close_done(self):
        calls = []
        calendar = {"ready": True}
        result, fake = self._run_skip_case(
            "realtime", calendar, trading_day=True, window="after_close_done", calls=calls
        )
        self._assert_skip_shape(result, task="realtime", reason="after_close_already_completed", run_date=FIXED_TODAY, fake_calendar=fake)
        self.assertEqual(calls, ["automatic_calendar", "is_trading_day", "realtime_window"])

    def test_per_call_freshness_no_shared_calendar_or_alignment(self):
        # Two consecutive automatic daily calls with DIFFERENT calendar objects:
        # neither the calendar nor the empty portfolioAlignment dict may be cached/shared.
        calls1: list[str] = []
        calls2: list[str] = []
        result1, cal1 = self._run_skip_case(
            "daily", {"ready": False, "reason": "r1"}, trading_day=True, window="session", calls=calls1, run_date=HISTORICAL_DATE
        )
        result2, cal2 = self._run_skip_case(
            "daily", {"ready": False, "reason": "r2"}, trading_day=True, window="session", calls=calls2, run_date=HISTORICAL_DATE
        )
        self.assertIsNot(result1["calendar"], result2["calendar"])
        self.assertIs(result1["calendar"], cal1)
        self.assertIs(result2["calendar"], cal2)
        self.assertIsNot(result1["portfolioAlignment"], result2["portfolioAlignment"])
        self.assertIsNot(result1, result2)

    def test_error_from_calendar_not_swallowed(self):
        def boom(_self, _date):
            raise RuntimeError("calendar refresh exploded")

        with (
            mock.patch.object(services.TaskController, "_automatic_calendar", boom),
            self.assertRaises(RuntimeError),
            mock.patch.object(services, "today_str", lambda: FIXED_TODAY),
        ):
            self.controller.run_task("daily", automatic=True, run_date=HISTORICAL_DATE)

    def test_non_automatic_daily_bypasses_gates(self):
        # automatic=False must skip the calendar/trading-day gates entirely and
        # reach the already-running runtime check (which we force-raise, no spawn).
        active = {"runId": "rt-1", "pid": 1}
        with (
            mock.patch.object(services, "get_active_runtime", lambda _home, _date: active),
            mock.patch.object(services, "today_str", lambda: FIXED_TODAY),
            self.assertRaises(AlreadyRunningError) as caught,
        ):
            self.controller.run_task("daily", run_date=HISTORICAL_DATE, automatic=False, force=False)
        self.assertIs(caught.exception.runtime, active)


if __name__ == "__main__":
    unittest.main()
