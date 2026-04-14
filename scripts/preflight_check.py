from __future__ import annotations

import argparse
import json
from datetime import time
from pathlib import Path

from common import (
    dump_json,
    ensure_layout,
    load_llm_config,
    load_project_toml,
    load_settings,
    load_strategy,
    preflight_result_path,
    resolve_agent_home,
    timestamp_now,
)
from multiagent_utils import build_llm_session, consume_sse_response, extract_response_output_text, resolve_api_key


KNOWN_INTRADAY_REPORT_MODES = {
    "intraday_proxy": "portfolio_report",
    "portfolio_report": "portfolio_report",
    "daily_report": "daily_report",
}


def parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _add_check(result: dict, name: str, status: str, detail: str, **extra) -> None:
    item = {"name": name, "status": status, "detail": detail}
    if extra:
        item.update(extra)
    result.setdefault("checks", []).append(item)
    if status == "error":
        result.setdefault("issues", []).append(f"{name}: {detail}")
    elif status == "warning":
        result.setdefault("warnings", []).append(f"{name}: {detail}")


def configured_python_path(agent_home: Path) -> str:
    project = load_project_toml(agent_home)
    runtime = project.get("runtime", {})
    candidate = str(runtime.get("python_executable", "") or "").strip()
    return candidate


def check_basic_layout(agent_home: Path, result: dict, scope: str) -> None:
    required = [
        agent_home / "config" / "settings.toml",
        agent_home / "config" / "strategy.toml",
        agent_home / "config" / "portfolio.json",
    ]
    if scope == "intraday":
        required.extend(
            [
                agent_home / "config" / "watchlist.json",
                agent_home / "config" / "llm.toml",
            ]
        )
    for path in required:
        if path.exists():
            _add_check(result, f"exists:{path.name}", "ok", f"已找到 {path}")
        else:
            _add_check(result, f"exists:{path.name}", "error", f"缺少关键文件 {path}")

    configured_python = configured_python_path(agent_home)
    if configured_python:
        path = Path(configured_python)
        if path.exists():
            _add_check(result, "python_config", "ok", f"project.toml 中配置的 Python 可用：{path}")
        else:
            _add_check(result, "python_config", "warning", f"project.toml 中配置了 Python，但路径不存在：{configured_python}")
    else:
        _add_check(result, "python_config", "warning", "project.toml 未配置 python_executable，将依赖启动脚本自动发现。")

    for name in ("temp", "cache", "logs"):
        directory = agent_home / name
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".okra_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            _add_check(result, f"writable:{name}", "ok", f"{directory} 可写")
        except Exception as exc:
            _add_check(result, f"writable:{name}", "error", f"{directory} 不可写：{exc}")


def check_schedule(agent_home: Path, result: dict) -> None:
    strategy = load_strategy(agent_home)
    schedule = strategy.get("schedule", {})
    for mode, start_key, end_key in (
        ("intraday", "intraday_start", "intraday_end"),
        ("nightly", "nightly_start", "nightly_end"),
    ):
        try:
            start_at = parse_clock(str(schedule[start_key]))
            end_at = parse_clock(str(schedule[end_key]))
        except Exception as exc:
            _add_check(result, f"schedule:{mode}", "error", f"{mode} 时间窗口配置无效：{exc}")
            continue
        if end_at <= start_at:
            _add_check(result, f"schedule:{mode}", "error", f"{mode} 结束时间必须晚于开始时间。")
        else:
            _add_check(result, f"schedule:{mode}", "ok", f"{mode} 时间窗口 {start_at.isoformat(timespec='minutes')} - {end_at.isoformat(timespec='minutes')}")

    run_if_missed = schedule.get("run_if_missed_on_next_boot")
    if isinstance(run_if_missed, bool):
        _add_check(result, "schedule:run_if_missed_on_next_boot", "ok", f"补跑配置为 {run_if_missed}")
    else:
        _add_check(result, "schedule:run_if_missed_on_next_boot", "warning", "run_if_missed_on_next_boot 未显式配置为布尔值。")

    report_mode = str(schedule.get("report_mode", "") or "").strip()
    if not report_mode:
        _add_check(result, "schedule:report_mode", "warning", "report_mode 为空，将回退到 intraday_proxy。")
    elif report_mode not in KNOWN_INTRADAY_REPORT_MODES:
        _add_check(result, "schedule:report_mode", "error", f"未识别的 report_mode：{report_mode}")
    else:
        _add_check(result, "schedule:report_mode", "ok", f"当前 intraday report_mode = {report_mode}")


def check_provider_config(agent_home: Path, result: dict) -> None:
    settings = load_settings(agent_home)
    providers = settings.get("providers", {})
    for section in ("quotes", "news", "intraday_proxy", "estimated_nav"):
        provider = providers.get(section, {})
        name = str(provider.get("name", "") or "").strip()
        timeout_seconds = provider.get("timeout_seconds")
        if not name:
            _add_check(result, f"provider:{section}", "error", f"{section} 缺少 provider name")
            continue
        _add_check(result, f"provider:{section}", "ok", f"{section} provider = {name}", timeout_seconds=timeout_seconds)


def probe_llm_model(agent_home: Path, config: dict) -> dict:
    provider = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config)
    payload = {
        "model": config["model"],
        "stream": True,
        "store": False,
        "max_output_tokens": 32,
        "reasoning": {"effort": "low"},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "Return strict JSON only."}]},
            {"role": "user", "content": [{"type": "input_text", "text": 'Return {"ok": true}.'}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "llm_probe",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
                "strict": True,
            }
        },
    }
    endpoint = provider["base_url"].rstrip("/") + "/responses"
    last_errors: list[str] = []
    for transport_name, use_env_proxy in (("direct", False), ("env_proxy", True)):
        session = build_llm_session(use_env_proxy=use_env_proxy)
        try:
            with session.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(10, 30),
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    detail = response.text[:500]
                    last_errors.append(f"{transport_name}: HTTP {response.status_code}: {detail}")
                    continue
                parsed_payload = consume_sse_response(response)
            completed = parsed_payload.get("completed_event") or {}
            if isinstance(completed, dict) and completed.get("response"):
                text = extract_response_output_text(completed["response"]).strip()
            else:
                text = extract_response_output_text(completed).strip()
            if not text:
                text = parsed_payload.get("output_text", "").strip()
            parsed = json.loads(text) if text else {}
            if parsed.get("ok") is True:
                return {
                    "status": "ok",
                    "transport_name": transport_name,
                    "detail": f"LLM probe 成功，model={config['model']}",
                }
            last_errors.append(f"{transport_name}: 返回成功响应，但内容不符合预期。")
        except Exception as exc:
            last_errors.append(f"{transport_name}: {exc}")
        finally:
            session.close()
    return {
        "status": "error",
        "transport_name": "",
        "detail": "LLM probe 失败：" + " | ".join(last_errors),
    }


def check_llm(agent_home: Path, result: dict, probe_network: bool) -> None:
    try:
        config = load_llm_config(agent_home)
    except Exception as exc:
        _add_check(result, "llm:config", "error", f"读取 llm.toml 失败：{exc}")
        return

    model_provider = str(config.get("model_provider", "") or "").strip()
    model = str(config.get("model", "") or "").strip()
    if not model_provider or model_provider not in config.get("model_providers", {}):
        _add_check(result, "llm:provider", "error", "model_provider 未配置或未在 model_providers 中定义。")
        return
    if not model:
        _add_check(result, "llm:model", "error", "model 为空。")
    else:
        _add_check(result, "llm:model", "ok", f"当前模型 = {model}")

    try:
        api_key = resolve_api_key(config)
        redacted = f"{api_key[:4]}***{api_key[-4:]}" if len(api_key) >= 8 else "***"
        _add_check(result, "llm:api_key", "ok", f"已解析 API key：{redacted}")
    except Exception as exc:
        _add_check(result, "llm:api_key", "error", str(exc))
        return

    if not probe_network:
        _add_check(result, "llm:probe", "warning", "已跳过联网模型探针。")
        return

    probe = probe_llm_model(agent_home, config)
    _add_check(
        result,
        "llm:probe",
        probe["status"],
        probe["detail"],
        transport_name=probe.get("transport_name", ""),
    )


def perform_preflight(agent_home: Path, scope: str, *, probe_llm: bool = True) -> dict:
    ensure_layout(agent_home)
    result = {
        "checked_at": timestamp_now(),
        "scope": scope,
        "status": "ok",
        "checks": [],
        "issues": [],
        "warnings": [],
    }
    check_basic_layout(agent_home, result, scope)
    check_schedule(agent_home, result)
    check_provider_config(agent_home, result)
    if scope in {"intraday", "desktop"}:
        check_llm(agent_home, result, probe_network=probe_llm)
    else:
        _add_check(result, "llm:probe", "warning", f"{scope} scope 默认不检查 LLM 连通性。")

    if result["issues"]:
        result["status"] = "failed"
    elif result["warnings"]:
        result["status"] = "warning"
    path = dump_json(preflight_result_path(agent_home), result)
    result["output_path"] = str(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preflight checks for okra assistant.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--scope", default="intraday", choices=["intraday", "nightly", "realtime", "desktop"])
    parser.add_argument("--skip-llm-probe", action="store_true", help="Skip the live LLM compatibility probe.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    result = perform_preflight(agent_home, args.scope, probe_llm=not args.skip_llm_probe)
    print(result["output_path"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "failed":
        raise SystemExit("preflight_failed")


if __name__ == "__main__":
    main()
