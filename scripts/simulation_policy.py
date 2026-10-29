"""Simulation advice deterministic policy (契约 docs/模拟研究助手优化方案.md §1/§2/§4/§5).

本模块**只做确定性、可单测的策略**：
- size_tier 枚举 -> 占冻结持仓 basis 的比例（前台不再让 LLM 报绝对金额）；
- state 优先级最严合并（blocked > degraded > shadow_only/approved，invalid fail-closed）；
- evidence_quality 与 confidence 分离建模；
- 决策 basis 冻结/复用（run_date + 基金键 + snapshot sha256），同日重复刷新复用旧 basis，
  不从修正后组合复利重取；
- legacy 建议识别（不按旧金额反推 tier）。

不在这里做 LLM 调用、不直接写官方路径；写盘仅由调用方在真正运行时触发。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

try:  # 原子写 + 文件锁（与项目其它产物一致）
    from common import dump_json, file_lock, lock_path
except Exception:  # pragma: no cover - 允许被独立单测导入
    dump_json = None
    file_lock = None
    lock_path = None

SCHEMA_VERSION = "simulation_v2"

_RUN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SIZE_TIERS = ("small", "medium", "large", "none")
DEFAULT_SIZE_RATIOS: dict[str, float] = {"small": 0.10, "medium": 0.25, "large": 0.50, "none": 0.0}

EVIDENCE_QUALITIES = ("high", "medium", "low", "unavailable")
VALID_DIRECTIONS = ("add", "reduce", "switch_out", "hold", "watch")
EXECUTABLE_DIRECTIONS = ("add", "reduce", "switch_out")

# state 优先级：数值越大越严。unknown 一律按最严处理（fail-closed）。
_STATE_PRIORITY: dict[str, int] = {"approved": 1, "shadow_only": 1, "degraded": 2, "blocked": 3}
_WORST_STATE = "blocked"

DEFAULT_TRADE_UNIT = 100.0


# --------------------------------------------------------------------------- #
# 枚举归一（invalid -> fail-closed）
# --------------------------------------------------------------------------- #
def normalize_size_tier(raw: Any) -> str:
    """把任意输入归一到合法 size_tier；非法/缺失 -> 'none'（即 hold，fail-closed）。"""
    tier = str(raw or "").strip().lower()
    if tier in SIZE_TIERS:
        return tier
    return "none"


def normalize_evidence_quality(raw: Any) -> str:
    """evidence_quality 归一；非法 -> 'unavailable'（最低档，fail-closed）。"""
    q = str(raw or "").strip().lower()
    if q in EVIDENCE_QUALITIES:
        return q
    return "unavailable"


def normalize_direction(raw: Any) -> str:
    d = str(raw or "").strip().lower()
    if d in VALID_DIRECTIONS:
        return d
    return "hold"


def strictest_state(*states: Any) -> str:
    """原 ticket / debate / former / hard-gate 状态取最严（契约 §5：blocked > degraded > shadow_only/approved）。

    - 缺失/空信号（None/""）视为"无此意见"，忽略；
    - 一旦出现**有值但不在枚举内**的状态 -> 立即 fail-closed 到 blocked；
    - 若一个有效信号都没有 -> blocked（无信息即不可交易）。
    """
    worst = "approved"
    saw = False
    for raw in states:
        state = str(raw or "").strip().lower()
        if not state:
            continue
        if state not in _STATE_PRIORITY:
            return _WORST_STATE  # present 但非法 -> fail-closed
        saw = True
        if _STATE_PRIORITY[state] > _STATE_PRIORITY[worst]:
            worst = state
    return worst if saw else _WORST_STATE


def state_allows_trade(state: str) -> bool:
    return strictest_state(state) in {"shadow_only", "approved"}


def validate_run_date(run_date: Any) -> str:
    """run_date 必须是 YYYY-MM-DD 且为真实日历日；拒绝路径逃逸/非法值。"""
    value = str(run_date or "").strip()
    if not _RUN_DATE_RE.match(value):
        raise ValueError(f"invalid run_date (expected YYYY-MM-DD): {run_date!r}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"invalid run_date (not a real date): {run_date!r}") from exc
    return value


def _finite(value: Any, *, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def load_simulation_config(agent_home: str | Path) -> dict[str, Any]:
    agent_home = Path(agent_home)
    path = agent_home / "config" / "simulation.toml"
    cfg: dict[str, Any] = {}
    if path.exists():
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    ratios = dict(DEFAULT_SIZE_RATIOS)
    for k, v in (cfg.get("size_tiers", {}) or {}).items():
        if k not in DEFAULT_SIZE_RATIOS:
            raise ValueError(f"unknown size_tier in simulation.toml: {k!r}")
        ratios[k] = _finite(v, default=DEFAULT_SIZE_RATIOS[k])
    # 有限 + 有序约束：0 <= small <= medium <= large <= 1，none 恒为 0（拒 NaN/乱序/越界）。
    ratios["none"] = 0.0
    for k in SIZE_TIERS:
        if not math.isfinite(ratios[k]):
            raise ValueError(f"size_ratio[{k}] is not finite")
    if not (0.0 <= ratios["small"] <= ratios["medium"] <= ratios["large"] <= 1.0):
        raise ValueError("size_tier ratios must satisfy 0<=small<=medium<=large<=1")
    unit = float((cfg.get("granularity", {}) or {}).get("trade_unit", DEFAULT_TRADE_UNIT) or DEFAULT_TRADE_UNIT)
    return {
        "funding_mode": str(cfg.get("funding_mode", "virtual_external_flows") or "virtual_external_flows"),
        "size_ratios": ratios,
        "trade_unit": unit,
    }


# --------------------------------------------------------------------------- #
# sizing：方向 + tier -> 内部金额（基于冻结 basis，不再用 LLM 绝对金额）
# --------------------------------------------------------------------------- #
def round_to_unit(amount: float, unit: float = DEFAULT_TRADE_UNIT) -> float:
    """仅 legacy 路径兼容用；新 simulation_v2 路径**不**走 100 元粒度。"""
    amount = max(0.0, float(amount or 0.0))
    if unit <= 0:
        return amount
    return float(int(amount // unit) * int(unit))


def sized_amount(basis_position_value: float, tier: str, *, size_ratios: dict[str, float] | None = None) -> float:
    """新 simulation_v2：内部金额 = 冻结持仓 basis × tier 比例，精确到分。

    明确**不做**（契约/本轮澄清）：
    - 不按 100 元粒度取整；
    - 不按 strategy max_add/max_reduce 每笔固定额截断；
    - 不按静态 cap_value 把档位恒截成旧额；
    - 不受 cash floor / gross / net 固定预算约束。
    仍保留的硬约束在下游：可卖额/非负、基金产品限制、集中度/目标仓位风险解释。
    """
    ratios = size_ratios or DEFAULT_SIZE_RATIOS
    ratio = float(ratios.get(tier, 0.0))
    basis = max(0.0, float(basis_position_value or 0.0))
    if not (math.isfinite(ratio) and math.isfinite(basis)):
        return 0.0
    return round(basis * ratio, 2)


def resolve_sized_direction(direction: str, tier: str, basis_position_value: float) -> dict[str, Any]:
    """零仓基金只允许 hold/watch（契约 §4，需人工建仓）。

    返回 {direction, size_tier, validated_amount, basis_position_value, zero_basis_gated}。
    对零仓下的 add/reduce/任意非 none tier 一律 fail-closed 到 hold/none。
    """
    direction = normalize_direction(direction)
    tier = normalize_size_tier(tier)
    basis = max(0.0, float(basis_position_value or 0.0))
    zero = basis <= 0.0
    gated = False
    if zero and direction in EXECUTABLE_DIRECTIONS:
        direction, tier, gated = "hold", "none", True
    # 合同：tier=none（零金额）时即便 LLM 报 add/reduce 也收敛为 hold，防"执行 0"。
    if tier == "none" and direction in EXECUTABLE_DIRECTIONS:
        direction, gated = "hold", True
    return {
        "direction": direction,
        "size_tier": tier,
        "validated_amount": 0.0,
        "basis_position_value": basis,
        "zero_basis_gated": gated,
    }


# --------------------------------------------------------------------------- #
# basis 冻结 / 复用
# --------------------------------------------------------------------------- #
def _canonical_source_snapshot(funds: dict[str, float]) -> list[dict[str, Any]]:
    rows = [{"fund_code": c, "basis_position_value": round(v, 2)} for c, v in funds.items()]
    rows.sort(key=lambda item: item["fund_code"])
    return rows


def _fingerprint_of_source_snapshot(source_snapshot: list[dict[str, Any]]) -> str:
    canonical = json.dumps({"source_snapshot": source_snapshot}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_fingerprint(portfolio: dict[str, Any]) -> str:
    funds = basis_funds_from_portfolio(portfolio)
    return _fingerprint_of_source_snapshot(_canonical_source_snapshot(funds))


def decision_basis_path(agent_home: str | Path, run_date: str) -> Path:
    run_date = validate_run_date(run_date)  # 拒路径逃逸/非法日期
    return Path(agent_home) / "db" / "decision_basis" / f"{run_date}.json"


def basis_funds_from_portfolio(portfolio: dict[str, Any]) -> dict[str, float]:
    funds: dict[str, float] = {}
    for f in portfolio.get("funds", []) or []:
        code = str(f.get("fund_code", "") or "")
        if code:
            v = float(f.get("current_value", 0.0) or 0.0)
            funds[code] = round(v, 2) if math.isfinite(v) else 0.0
    return funds


def build_decision_basis(run_date: str, portfolio: dict[str, Any],
                         *, decision_at: str | None = None) -> dict[str, Any]:
    run_date = validate_run_date(run_date)
    funds = basis_funds_from_portfolio(portfolio)
    source_snapshot = _canonical_source_snapshot(funds)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_date": run_date,
        "decision_at": decision_at or datetime.now(timezone.utc).isoformat(),
        "source_snapshot": source_snapshot,
        "snapshot_sha256": _fingerprint_of_source_snapshot(source_snapshot),
        "funds": funds,
    }


def _verify_basis_integrity(cached: dict[str, Any], run_date: str) -> None:
    """校验 manifest 自洽：source_snapshot 重算指纹须 == 记录值，且 funds 与 source_snapshot 一致。"""
    if cached.get("run_date") != run_date:
        raise ValueError(f"decision basis run_date mismatch: {cached.get('run_date')} != {run_date}")
    source = cached.get("source_snapshot")
    if not isinstance(source, list) or not source:
        raise ValueError("decision basis manifest corrupt: missing source_snapshot")
    recorded = cached.get("snapshot_sha256")
    if not isinstance(recorded, str) or recorded != _fingerprint_of_source_snapshot(source):
        raise ValueError("decision basis tampered: snapshot_sha256 does not match source_snapshot")
    funds = cached.get("funds")
    if not isinstance(funds, dict):
        raise ValueError("decision basis manifest corrupt: missing funds")
    rebuilt = {row["fund_code"]: round(float(row["basis_position_value"]), 2) for row in source}
    if rebuilt != {k: round(float(v), 2) for k, v in funds.items()}:
        raise ValueError("decision basis tampered: funds inconsistent with source_snapshot")


def get_or_freeze_basis(agent_home: str | Path, run_date: str, portfolio: dict[str, Any],
                        *, write: bool = False, decision_at: str | None = None) -> dict[str, Any]:
    """同日重复运行**复用**已冻结 basis；漂移后的实时组合绝不复利重算。

    - 已存在 manifest：先做完整性/指纹自洽校验，通过即复用，**不**与漂移后实时组合比对。
    - 缺失 = 新决策周期：用决策前快照冻结；write=True 才加锁 + 原子落盘（仅真实运行）。
    - 篡改/自相矛盾 -> fail-closed。
    """
    run_date = validate_run_date(run_date)
    agent_home = Path(agent_home)
    path = decision_basis_path(agent_home, run_date)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        _verify_basis_integrity(cached, run_date)
        return cached
    expected = build_decision_basis(run_date, portfolio, decision_at=decision_at)
    if write:
        if file_lock is None or dump_json is None:
            raise RuntimeError("atomic dump/lock unavailable; refusing non-atomic basis write")
        with file_lock(lock_path(agent_home, f"decision_basis_{run_date}")):
            # 二次检查：锁内若已被并发写入则复用，避免覆盖
            if path.exists():
                cached = json.loads(path.read_text(encoding="utf-8"))
                _verify_basis_integrity(cached, run_date)
                return cached
            dump_json(path, expected)
    return expected


def basis_value_for(basis: dict[str, Any], fund_code: str) -> float:
    return round(max(0.0, float((basis.get("funds", {}) or {}).get(fund_code, 0.0) or 0.0)), 2)


# --------------------------------------------------------------------------- #
# legacy 识别（不按旧金额反推 tier）
# --------------------------------------------------------------------------- #
def is_legacy_advice(advice: dict[str, Any]) -> bool:
    """无 simulation_v2 schema_version 即视为 legacy；调用方不得从其金额反推 tier。"""
    return str(advice.get("schema_version", "") or "") != SCHEMA_VERSION
