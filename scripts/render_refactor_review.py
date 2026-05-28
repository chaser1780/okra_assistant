from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from artifact_boundary import assert_refactor_write_allowed, relative_posix
from common import resolve_agent_home, resolve_date, timestamp_now, validated_advice_path


REVIEW_SCHEMA_VERSION = "refactor_review_markdown.v1"


def refactor_review_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "refactor_reviews" / f"{report_date}.md"


def action_ticket_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_tickets" / f"{report_date}.json"


def retrieval_pack_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "retrieval_packs" / f"{report_date}.json"


def action_debate_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_debates" / f"{report_date}.json"


def outcome_event_path(agent_home: Path, report_date: str, horizon: str) -> Path:
    safe_horizon = str(horizon).replace("/", "_").replace("\\", "_").replace(":", "_")
    return agent_home / "db" / "outcome_events" / f"{report_date}__{safe_horizon}.json"


def read_json_artifact(path: Path) -> tuple[dict[str, Any], str, str]:
    if not path.exists():
        return {}, "not_run", "missing artifact"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, "failed", f"invalid artifact: {exc}"
    if not isinstance(payload, dict):
        return {}, "failed", "artifact root is not an object"
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    status = str(summary.get("status", "") or "")
    if status in {"degraded", "failed", "missing_inputs"}:
        return payload, "degraded", status
    return payload, "ready", "loaded"


def md_escape(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("\n", " ").replace("|", "\\|")


def short_text(value: Any, limit: int = 100) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def fmt_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def fmt_num(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def source_artifact_status(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    return f"write_scope={payload.get('write_scope', '')}; non_executable={fmt_bool(payload.get('non_executable'))}"


def official_actions(validated: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for bucket in ("tactical_actions", "dca_actions", "hold_actions"):
        for item in validated.get(bucket, []) or []:
            if isinstance(item, dict):
                copied = dict(item)
                copied["_bucket"] = bucket
                actions.append(copied)
    return actions


def official_action_by_code(validated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for action in official_actions(validated):
        code = str(action.get("fund_code", "") or "")
        if code:
            by_code.setdefault(code, action)
    return by_code


def tickets_by_code(action_tickets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("fund_code", "") or ""): item
        for item in action_tickets.get("tickets", []) or []
        if isinstance(item, dict) and item.get("fund_code")
    }


def packs_by_ticket_id(retrieval_packs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pack in retrieval_packs.get("packs", []) or []:
        if not isinstance(pack, dict):
            continue
        target = pack.get("target", {}) if isinstance(pack.get("target"), dict) else {}
        ticket_id = str(target.get("ticket_id", "") or "")
        if ticket_id:
            result[ticket_id] = pack
    return result


def debates_by_ticket_id(action_debates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("ticket_id", "") or ""): item
        for item in action_debates.get("debates", []) or []
        if isinstance(item, dict) and item.get("ticket_id")
    }


def outcomes_by_ticket_id(outcome_artifacts: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for horizon, artifact in outcome_artifacts.items():
        for item in artifact.get("events", []) or []:
            if not isinstance(item, dict) or not item.get("ticket_id"):
                continue
            copied = dict(item)
            copied["_horizon"] = horizon
            result.setdefault(str(copied["ticket_id"]), []).append(copied)
    return result


def guardrail_counts(ticket: dict[str, Any]) -> dict[str, int]:
    counts = {"pass": 0, "adjust": 0, "block": 0, "not_checked": 0}
    for item in ticket.get("hard_guardrail_results", []) or []:
        if not isinstance(item, dict):
            continue
        result = str(item.get("result", "") or "")
        counts[result] = counts.get(result, 0) + 1
    return counts


def pack_trace_status(pack: dict[str, Any]) -> str:
    if not pack:
        return "not_run"
    audit = pack.get("audit", {}) if isinstance(pack.get("audit"), dict) else {}
    trace_rate = audit.get("trace_completeness_rate")
    if trace_rate is None:
        trace_rate = pack.get("trace_completeness_rate")
    missing_count = len(pack.get("missing_data", []) or [])
    rag_count = len(pack.get("rag_trace_refs", []) or [])
    return f"trace={fmt_num(trace_rate)}; missing={missing_count}; rag_refs={rag_count}"


def debate_status(debate: dict[str, Any]) -> str:
    if not debate:
        return "not_run"
    outputs = debate.get("node_outputs", {}) if isinstance(debate.get("node_outputs"), dict) else {}
    referee = outputs.get("debate_referee", {}) if isinstance(outputs.get("debate_referee"), dict) else {}
    verdict = str(referee.get("verdict", "") or "")
    status = str(debate.get("ticket_status", "") or "")
    degraded = "degraded" if debate.get("degraded") else "ok"
    pieces = [piece for piece in (status, verdict, degraded) if piece]
    return "; ".join(pieces)


def proposed_patch_status(debate: dict[str, Any]) -> str:
    outputs = debate.get("node_outputs", {}) if isinstance(debate.get("node_outputs"), dict) else {}
    writer = outputs.get("ticket_writer", {}) if isinstance(outputs.get("ticket_writer"), dict) else {}
    patch = writer.get("proposed_ticket_patch", {}) if isinstance(writer.get("proposed_ticket_patch"), dict) else {}
    if not patch:
        return ""
    return (
        f"mutation_mode={patch.get('mutation_mode', '')}; "
        f"non_executable={fmt_bool(patch.get('non_executable'))}; "
        f"writes_ticket_file={fmt_bool(writer.get('writes_ticket_file'))}"
    )


def outcome_status(events: list[dict[str, Any]]) -> str:
    if not events:
        return "not_run"
    parts = []
    for event in sorted(events, key=lambda item: str(item.get("_horizon", ""))):
        parts.append(
            f"{event.get('_horizon')}:"
            f"{event.get('scoring_status', '')}/"
            f"{event.get('outcome_label', '')}/"
            f"{fmt_num(event.get('actual_return_pct'))}"
        )
    return "; ".join(parts)


def official_action_label(action: dict[str, Any]) -> str:
    if not action:
        return "none"
    return str(action.get("validated_action", "") or "none")


def shadow_action_label(ticket: dict[str, Any]) -> str:
    if not ticket:
        return "not_run"
    return str(ticket.get("action_verb", "") or "not_run")


def official_shadow_diff(validated: dict[str, Any], action_tickets: dict[str, Any]) -> dict[str, Any]:
    official_by_code = official_action_by_code(validated)
    ticket_map = tickets_by_code(action_tickets)
    codes = sorted(set(official_by_code) | set(ticket_map))
    mismatches = [
        {
            "fund_code": code,
            "official_action": official_action_label(official_by_code.get(code, {})),
            "shadow_action": shadow_action_label(ticket_map.get(code, {})),
        }
        for code in codes
        if official_action_label(official_by_code.get(code, {})) != shadow_action_label(ticket_map.get(code, {}))
    ]
    return {
        "compared_fund_count": len(codes),
        "matched_action_count": len(codes) - len(mismatches),
        "mismatched_action_count": len(mismatches),
        "mismatches": mismatches,
    }


def official_shadow_diff_lines(validated: dict[str, Any], action_tickets: dict[str, Any]) -> list[str]:
    diff = official_shadow_diff(validated, action_tickets)
    lines = [
        "- This review compares official validated actions against shadow action tickets for the same report_date.",
        "- It does not judge investment correctness and does not promote shadow output.",
        f"- compared_fund_count: {diff['compared_fund_count']}",
        f"- matched_action_count: {diff['matched_action_count']}",
        f"- mismatched_action_count: {diff['mismatched_action_count']}",
    ]
    mismatches = diff["mismatches"]
    if mismatches:
        lines.append("- mismatches:")
        for item in mismatches[:10]:
            lines.append(f"  - {item['fund_code']}: official={item['official_action']} shadow={item['shadow_action']}")
        if len(mismatches) > 10:
            lines.append(f"  - ... {len(mismatches) - 10} more")
    return lines


def artifact_rows(artifacts: dict[str, tuple[Path, dict[str, Any], str, str]], agent_home: Path) -> list[str]:
    rows = ["| Artifact | Path | State | Detail | Boundary |", "|---|---|---|---|---|"]
    for name, (path, payload, state, detail) in artifacts.items():
        rows.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    name,
                    relative_posix(path, agent_home),
                    state,
                    detail,
                    source_artifact_status(payload),
                )
            )
            + " |"
        )
    return rows


def artifact_summary_lines(name: str, payload: dict[str, Any], state: str, detail: str) -> list[str]:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    if name == "validated_advice":
        return [
            f"- status: {state} ({detail})",
            f"- generated_at: {payload.get('generated_at', '')}",
            f"- decision_mode: {payload.get('decision_mode', '')}",
            f"- execution_eligible: {fmt_bool(payload.get('execution_eligible'))}",
            f"- official action count: {len(official_actions(payload))}",
        ]
    return [
        f"- status: {state} ({detail})",
        f"- generated_at: {payload.get('generated_at', '')}",
        f"- {source_artifact_status(payload)}",
        f"- summary: {json.dumps(summary, ensure_ascii=False, sort_keys=True)}",
    ]


def guardrail_map_lines(ticket_map: dict[str, dict[str, Any]]) -> list[str]:
    rows = ["| Fund | Ticket Status | Pass | Adjust | Block | Not Checked | Missing Data |", "|---|---|---:|---:|---:|---:|---:|"]
    for code in sorted(ticket_map):
        ticket = ticket_map[code]
        counts = guardrail_counts(ticket)
        rows.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    code,
                    ticket.get("ticket_status", ""),
                    counts.get("pass", 0),
                    counts.get("adjust", 0),
                    counts.get("block", 0),
                    counts.get("not_checked", 0),
                    len(ticket.get("missing_data", []) or []),
                )
            )
            + " |"
        )
    if len(rows) == 2:
        rows.append("| _none_ |  | 0 | 0 | 0 | 0 | 0 |")
    return rows


def fund_review_rows(
    validated: dict[str, Any],
    action_tickets: dict[str, Any],
    retrieval_packs: dict[str, Any],
    action_debates: dict[str, Any],
    outcome_artifacts: dict[str, dict[str, Any]],
) -> list[str]:
    official_by_code = official_action_by_code(validated)
    ticket_map = tickets_by_code(action_tickets)
    pack_map = packs_by_ticket_id(retrieval_packs)
    debate_map = debates_by_ticket_id(action_debates)
    outcome_map = outcomes_by_ticket_id(outcome_artifacts)
    codes = sorted(set(official_by_code) | set(ticket_map))
    rows = [
        "| Fund | Official | Shadow Ticket | Amount | Guardrails | Retrieval Trace | Debate | Outcome | Proposed Patch | Thesis |",
        "|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for code in codes:
        official = official_by_code.get(code, {})
        ticket = ticket_map.get(code, {})
        ticket_id = str(ticket.get("ticket_id", "") or "")
        pack = pack_map.get(ticket_id)
        debate = debate_map.get(ticket_id)
        counts = guardrail_counts(ticket)
        guardrails = f"block={counts.get('block', 0)}, adjust={counts.get('adjust', 0)}, not_checked={counts.get('not_checked', 0)}"
        rows.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    f"{code} {ticket.get('fund_name') or official.get('fund_name', '')}",
                    f"{official.get('validated_action', '')} ({official.get('_bucket', '')})",
                    f"{ticket.get('action_verb', '')} / {ticket.get('ticket_status', 'not_run')}",
                    fmt_num(ticket.get("validated_amount")),
                    guardrails,
                    pack_trace_status(pack or {}),
                    debate_status(debate or {}),
                    outcome_status(outcome_map.get(ticket_id, [])),
                    proposed_patch_status(debate or {}),
                    short_text(ticket.get("thesis", "") or official.get("thesis", ""), 90),
                )
            )
            + " |"
        )
    if len(rows) == 2:
        rows.append("| _none_ |  |  |  |  |  |  |  |  |  |")
    return rows


def outcome_summary_lines(outcome_artifacts: dict[str, tuple[Path, dict[str, Any], str, str]]) -> list[str]:
    rows = ["| Horizon | State | Event Count | Scored | Pending | Blocked | Detail |", "|---|---|---:|---:|---:|---:|---|"]
    for horizon, (_path, payload, state, detail) in outcome_artifacts.items():
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        rows.append(
            "| "
            + " | ".join(
                md_escape(value)
                for value in (
                    horizon,
                    state,
                    summary.get("event_count", 0),
                    summary.get("scored_count", 0),
                    summary.get("pending_count", 0),
                    summary.get("blocked_count", 0),
                    detail,
                )
            )
            + " |"
        )
    return rows


def open_questions(
    artifact_states: dict[str, tuple[Path, dict[str, Any], str, str]],
    action_tickets: dict[str, Any],
    retrieval_packs: dict[str, Any],
    action_debates: dict[str, Any],
    outcome_payloads: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    questions: list[str] = []
    for name, (_path, _payload, state, detail) in artifact_states.items():
        if state != "ready":
            questions.append(f"- {name}: {state} ({detail})")
    ticket_summary = action_tickets.get("summary", {}) if isinstance(action_tickets.get("summary"), dict) else {}
    pack_summary = retrieval_packs.get("summary", {}) if isinstance(retrieval_packs.get("summary"), dict) else {}
    debate_summary = action_debates.get("summary", {}) if isinstance(action_debates.get("summary"), dict) else {}
    if ticket_summary.get("degraded_count"):
        questions.append(f"- action_tickets: degraded_count={ticket_summary.get('degraded_count')}")
    if pack_summary.get("missing_data_count"):
        questions.append(f"- retrieval_packs: missing_data_count={pack_summary.get('missing_data_count')}")
    if debate_summary.get("node_failure_count"):
        questions.append(f"- action_debates: node_failure_count={debate_summary.get('node_failure_count')}")
    if debate_summary.get("writes_ticket_file") is not False and action_debates:
        questions.append("- action_debates: writes_ticket_file is not false")
    for horizon, payload in (outcome_payloads or {}).items():
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        if summary.get("pending_count"):
            questions.append(f"- outcome_events {horizon}: pending_count={summary.get('pending_count')}")
        if summary.get("blocked_count"):
            questions.append(f"- outcome_events {horizon}: blocked_count={summary.get('blocked_count')}")
    if not questions:
        questions.append("- No blocking review question detected by the Markdown renderer.")
    return questions


def overall_status(artifact_states: dict[str, tuple[Path, dict[str, Any], str, str]], optional_states: dict[str, tuple[Path, dict[str, Any], str, str]] | None = None) -> str:
    states = [state for _path, _payload, state, _detail in artifact_states.values()]
    optional_loaded_states = [state for _path, _payload, state, _detail in (optional_states or {}).values() if state != "not_run"]
    states.extend(optional_loaded_states)
    if any(state == "failed" for state in states):
        return "failed"
    if any(state == "degraded" for state in states):
        return "degraded"
    if any(state == "not_run" for state in states):
        return "partial" if any(state == "ready" for state in states) else "not_run"
    return "ready"


def review_payload(report_date: str, generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "artifact_id": f"refactor_review:{report_date}",
        "artifact_kind": "refactor_review_markdown",
        "report_date": report_date,
        "generated_at": generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "display_only": True,
    }


def render_markdown(agent_home: Path, report_date: str, *, generated_at: str | None = None) -> str:
    generated_at = generated_at or timestamp_now()
    paths = {
        "validated_advice": validated_advice_path(agent_home, report_date),
        "action_tickets": action_ticket_path(agent_home, report_date),
        "retrieval_packs": retrieval_pack_path(agent_home, report_date),
        "action_debates": action_debate_path(agent_home, report_date),
    }
    outcome_paths = {
        "T+1": outcome_event_path(agent_home, report_date, "T+1"),
        "T+5": outcome_event_path(agent_home, report_date, "T+5"),
    }
    artifact_states = {
        name: (path, *read_json_artifact(path))
        for name, path in paths.items()
    }
    outcome_states = {
        horizon: (path, *read_json_artifact(path))
        for horizon, path in outcome_paths.items()
    }
    validated = artifact_states["validated_advice"][1]
    action_tickets = artifact_states["action_tickets"][1]
    retrieval_packs = artifact_states["retrieval_packs"][1]
    action_debates = artifact_states["action_debates"][1]
    outcome_payloads = {horizon: item[1] for horizon, item in outcome_states.items() if item[2] != "not_run"}
    review_status = overall_status(artifact_states, outcome_states)

    lines = [
        f"# Refactor Shadow Review {report_date}",
        "",
        f"- status: {review_status}",
        f"- generated_at: {generated_at}",
        "- display_only: true",
        "- non_executable: true",
        "- writes_official_outputs: false",
        "- scope: validated_advice -> action_ticket -> retrieval_pack -> action_debate -> outcome_event",
        "",
        "## Artifact Status",
        *artifact_rows(artifact_states, agent_home),
        "",
        "## Outcome Event Status",
        *outcome_summary_lines(outcome_states),
        "",
        "## Official Validated Advice Summary",
        *artifact_summary_lines("validated_advice", *artifact_states["validated_advice"][1:]),
        "",
        "## Shadow Action Ticket Summary",
        *artifact_summary_lines("action_tickets", *artifact_states["action_tickets"][1:]),
        "",
        "## Retrieval Trace Completeness",
        *artifact_summary_lines("retrieval_packs", *artifact_states["retrieval_packs"][1:]),
        "",
        "## Action Debate Status",
        *artifact_summary_lines("action_debates", *artifact_states["action_debates"][1:]),
        "",
        "## Fund Review Tickets",
        *fund_review_rows(validated, action_tickets, retrieval_packs, action_debates, outcome_payloads),
        "",
        "## Guardrail Map",
        *guardrail_map_lines(tickets_by_code(action_tickets)),
        "",
        "## Diff Versus Official",
        *official_shadow_diff_lines(validated, action_tickets),
        "",
        "## Boundary Check Result",
        "- shadow write path: db/refactor_reviews/<report_date>.md",
        "- write_scope: shadow_only",
        "- non_executable: true",
        "- display_only: true",
        "- execution mutation path: none",
        "",
        "## Open Questions",
        *open_questions(artifact_states, action_tickets, retrieval_packs, action_debates, outcome_payloads),
        "",
    ]
    return "\n".join(lines)


def write_review_markdown(agent_home: Path, report_date: str, markdown: str, *, generated_at: str | None = None) -> Path:
    generated_at = generated_at or timestamp_now()
    path = refactor_review_path(agent_home, report_date)
    assert_refactor_write_allowed(path, review_payload(report_date, generated_at), agent_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8", newline="\n")
    return path


def run_renderer(agent_home: Path, report_date: str, *, generated_at: str | None = None) -> tuple[Path, str]:
    generated_at = generated_at or timestamp_now()
    markdown = render_markdown(agent_home, report_date, generated_at=generated_at)
    path = write_review_markdown(agent_home, report_date, markdown, generated_at=generated_at)
    return path, markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a display-only Markdown review from refactor shadow artifacts.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD.")
    parser.add_argument("--generated-at", default="", help="Optional fixed generated_at timestamp for deterministic tests.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    path, markdown = run_renderer(agent_home, report_date, generated_at=args.generated_at or None)
    status_line = next((line for line in markdown.splitlines() if line.startswith("- status: ")), "- status: unknown")
    print(f"wrote refactor review ({status_line.removeprefix('- status: ')}): {relative_posix(path, agent_home)}")


if __name__ == "__main__":
    main()
