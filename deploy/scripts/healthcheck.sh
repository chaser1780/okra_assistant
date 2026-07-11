#!/usr/bin/env bash
set -euo pipefail

AGENT_HOME="${FUND_AGENT_HOME:-/opt/okra_assistant}"
BASE_URL="${OKRA_HEALTHCHECK_BASE_URL:-http://127.0.0.1:8765}"
MODE="api"
REPORT_DATE=""
DRY_RUN=0
TIMEOUT_SECONDS=10

usage() {
  cat <<'EOF'
Usage: healthcheck.sh [--mode api|daily|realtime] [--agent-home PATH]
                      [--base-url URL] [--date YYYY-MM-DD] [--dry-run]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "--mode requires a value" >&2; exit 2; }
      MODE="$2"
      shift 2
      ;;
    --agent-home)
      [[ $# -ge 2 ]] || { echo "--agent-home requires a value" >&2; exit 2; }
      AGENT_HOME="$2"
      shift 2
      ;;
    --base-url)
      [[ $# -ge 2 ]] || { echo "--base-url requires a value" >&2; exit 2; }
      BASE_URL="$2"
      shift 2
      ;;
    --date)
      [[ $# -ge 2 ]] || { echo "--date requires a value" >&2; exit 2; }
      REPORT_DATE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  api|daily|realtime) ;;
  *) echo "invalid mode: $MODE" >&2; exit 2 ;;
esac
case "$BASE_URL" in
  http://*|https://*) ;;
  *) echo "base URL must use http or https" >&2; exit 2 ;;
esac
[[ "$BASE_URL" != *[$'\r\n\t ']* ]] || { echo "base URL contains whitespace" >&2; exit 2; }
BASE_URL="${BASE_URL%/}"
AGENT_HOME="$(realpath -e -- "$AGENT_HOME")"
[[ "$AGENT_HOME" != "/" ]] || { echo "agent home cannot be /" >&2; exit 2; }

if [[ -z "$REPORT_DATE" ]]; then
  REPORT_DATE="$(TZ=Asia/Shanghai date +%F)"
fi
[[ "$REPORT_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "invalid report date" >&2; exit 2; }

artifact=""
page_url=""
if [[ "$MODE" == "daily" ]]; then
  artifact="db/validated_advice/$REPORT_DATE.json"
  page_url="$BASE_URL/api/today?date=$REPORT_DATE"
elif [[ "$MODE" == "realtime" ]]; then
  artifact="db/realtime_monitor/$REPORT_DATE.json"
  page_url="$BASE_URL/api/realtime?date=$REPORT_DATE"
fi

if [[ -n "$artifact" ]]; then
  artifact_path="$(realpath -m -- "$AGENT_HOME/$artifact")"
  case "$artifact_path" in
    "$AGENT_HOME"/*) ;;
    *) echo "artifact path escapes agent home" >&2; exit 2 ;;
  esac
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "health_url=$BASE_URL/api/health"
  [[ -n "$page_url" ]] && echo "page_url=$page_url"
  [[ -n "$artifact" ]] && echo "artifact=$artifact"
  exit 0
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
curl --fail --silent --show-error --max-time "$TIMEOUT_SECONDS" "$BASE_URL/api/health" > "$tmp_dir/health.json"
python3 - "$tmp_dir/health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("ok") is False:
    raise SystemExit("health endpoint returned ok=false")
data = payload.get("data", payload)
if isinstance(data, dict) and data.get("status") in {"error", "failed", "unhealthy"}:
    raise SystemExit("health endpoint reported an unhealthy status")
PY

if [[ -n "$artifact" ]]; then
  [[ -s "$artifact_path" ]] || { echo "missing or empty artifact: $artifact_path" >&2; exit 1; }
  page_curl_args=(--fail --silent --show-error --max-time "$TIMEOUT_SECONDS")
  if [[ -n "${OKRA_API_TOKEN:-}" ]]; then
    [[ "$OKRA_API_TOKEN" != *[$'\r\n']* ]] || { echo "OKRA_API_TOKEN contains an invalid newline" >&2; exit 2; }
    auth_header="$tmp_dir/authorization.header"
    printf 'Authorization: Bearer %s\n' "$OKRA_API_TOKEN" > "$auth_header"
    chmod 0600 "$auth_header"
    page_curl_args+=(--header "@$auth_header")
  fi
  curl "${page_curl_args[@]}" "$page_url" > "$tmp_dir/page.json"
  python3 - "$tmp_dir/page.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("ok") is False:
    raise SystemExit("page endpoint returned ok=false")
PY
fi

echo "okra_healthcheck=ok mode=$MODE date=$REPORT_DATE"
