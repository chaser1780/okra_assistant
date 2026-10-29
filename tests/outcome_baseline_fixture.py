"""Deterministic synthetic inputs for test_outcome_evidence_baseline.

Generates a portable TempAgentHome fixture: a synthetic-only trading calendar,
validated advice (scheduled_dca + hold), portfolio snapshot, and official-nav
quotes — no real db copy, no private paths, no network.

NOTE: this calendar is a synthetic test artifact and does NOT describe the
product's real trading calendar. Returns data is fixed; only the freshness
clock (checked_at) is wall-clock. Counts are engineered so the outcome baseline
builder produces >=20 scored events across T+1 / T+5.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPORT_DATE = "2026-05-22"
# Trading-day nav grid (product calendar is NOT real here; synthetic fixture only):
#   2026-05-22 (Fri) base, 2026-05-25 (Mon) T+1 target day, 2026-05-29 (Fri) T+5 evaluation day.
QUOTE_DATES = ["2026-05-22", "2026-05-25", "2026-05-29"]
FUND_CODES = [f"9000{idx:03d}" for idx in range(1, 13)]
DCA_CODES = FUND_CODES[:6]
NAV_BY_DATE = {"2026-05-22": 1.0000, "2026-05-25": 1.0100, "2026-05-29": 1.0300}


def _write_json(root: Path, relative: str, payload: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")


def write_synthetic_inputs(root: Path) -> None:
    """Write all inputs the outcome baseline pipeline reads under root."""
    calendar = {
        "source": "synthetic_test_calendar_not_product_calendar",
        "coverage_start": "2026-05-01",
        "coverage_end": "2026-06-30",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_json(root, "config/trading_calendar.json", calendar)

    dca_actions = [
        {
            "fund_code": code,
            "fund_name": f"合成基金{code}",
            "validated_action": "scheduled_dca",
            "model_action": "scheduled_dca",
            "validated_amount": 1000.0,
            "thesis": "synthetic dca seed",
        }
        for code in DCA_CODES
    ]
    validated = {
        "generated_at": "2026-05-22T18:00:00+08:00",
        "decision_mode": "canonical",
        "execution_eligible": True,
        "committee_decision_bundle": {"fund_decisions": []},
        "tactical_actions": [],
        "dca_actions": dca_actions,
        "hold_actions": [],
    }
    _write_json(root, f"db/validated_advice/{REPORT_DATE}.json", validated)

    portfolio = {
        "as_of_date": REPORT_DATE,
        "total_value": 120000.0,
        "funds": [
            {
                "fund_code": code,
                "fund_name": f"合成基金{code}",
                "holding_units": 10000.0,
                "units_source": "stored",
                "current_value": 10000.0,
                "as_of_date": REPORT_DATE,
            }
            for code in FUND_CODES
        ],
    }
    _write_json(root, f"db/portfolio_state/snapshots/{REPORT_DATE}.json", portfolio)

    for date in QUOTE_DATES:
        nav = NAV_BY_DATE[date]
        quote = {
            "generated_at": f"{date}T20:00:00+08:00",
            "funds": [
                {
                    "code": code,
                    "as_of_date": date,
                    "nav": nav,
                }
                for code in FUND_CODES
            ],
        }
        _write_json(root, f"raw/quotes/{date}.json", quote)
