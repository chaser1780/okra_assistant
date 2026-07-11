#!/usr/bin/env bash
set -euo pipefail

AGENT_HOME="${FUND_AGENT_HOME:-/opt/okra_assistant}"
OUTPUT_DIR="/var/backups/okra"
RCLONE_DESTINATION="${OKRA_RCLONE_BACKUP_DEST:-}"
STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
EXECUTE=0
CONFIRM_PRIVATE_DATA=0

usage() {
  cat <<'EOF'
Usage: backup_artifacts.sh [--agent-home PATH] [--output-dir PATH]
                           [--timestamp YYYY-MM-DDTHHMMSSZ]
                           [--rclone-destination REMOTE:PREFIX]
                           [--execute --confirm-private-data]

Default behavior is a dry run. Backups contain private portfolio and execution
state but never intentionally include API keys, cookies, browser profiles, or
raw account screenshots. Use only a private/encrypted destination.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-home)
      [[ $# -ge 2 ]] || { echo "--agent-home requires a value" >&2; exit 2; }
      AGENT_HOME="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { echo "--output-dir requires a value" >&2; exit 2; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --timestamp)
      [[ $# -ge 2 ]] || { echo "--timestamp requires a value" >&2; exit 2; }
      STAMP="$2"
      shift 2
      ;;
    --rclone-destination)
      [[ $# -ge 2 ]] || { echo "--rclone-destination requires a value" >&2; exit 2; }
      RCLONE_DESTINATION="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --confirm-private-data)
      CONFIRM_PRIVATE_DATA=1
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

[[ "$STAMP" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || { echo "invalid timestamp" >&2; exit 2; }
AGENT_HOME="$(realpath -e -- "$AGENT_HOME")"
OUTPUT_DIR="$(realpath -m -- "$OUTPUT_DIR")"
[[ "$AGENT_HOME" != "/" && "$OUTPUT_DIR" != "/" ]] || { echo "agent home/output cannot be /" >&2; exit 2; }
case "$OUTPUT_DIR" in
  "$AGENT_HOME"|"$AGENT_HOME"/*)
    echo "backup output must be outside agent home to prevent recursive capture" >&2
    exit 2
    ;;
esac
case "$AGENT_HOME" in
  "$OUTPUT_DIR"/*)
    echo "backup output cannot be an ancestor of agent home" >&2
    exit 2
    ;;
esac
if [[ -n "$RCLONE_DESTINATION" ]]; then
  [[ "$RCLONE_DESTINATION" == *:* ]] || { echo "rclone destination must use REMOTE:PREFIX syntax" >&2; exit 2; }
  [[ "$RCLONE_DESTINATION" != *[$'\r\n\t ']* ]] || { echo "rclone destination contains whitespace" >&2; exit 2; }
  [[ "$RCLONE_DESTINATION" != replace-with-* ]] || { echo "replace the rclone destination placeholder first" >&2; exit 2; }
fi
if [[ "$EXECUTE" -eq 1 && "$CONFIRM_PRIVATE_DATA" -ne 1 ]]; then
  echo "--execute requires --confirm-private-data" >&2
  exit 2
fi

include_paths=(
  db/long_memory
  db/execution_sync
  db/portfolio_state
  db/validated_advice
  db/decision_ledger
  db/decision_latest
  db/decisions
  raw/news
  reports/daily
  config/agents.toml
  config/benchmark_mappings.json
  config/portfolio.json
  config/production.toml
  config/rag.toml
  config/realtime_valuation.toml
  config/retention.toml
  config/review.toml
  config/settings.toml
  config/strategy.toml
  config/trading_calendar.json
  config/watchlist.json
  deploy
  project.toml
  requirements.txt
)

echo "backup_mode=$([[ "$EXECUTE" -eq 1 ]] && echo execute || echo dry-run)"
echo "agent_home=$AGENT_HOME"
echo "output_dir=$OUTPUT_DIR"
for relative in "${include_paths[@]}"; do
  candidate="$(realpath -m -- "$AGENT_HOME/$relative")"
  case "$candidate" in
    "$AGENT_HOME"/*) ;;
    *) echo "include path escapes agent home: $relative" >&2; exit 2 ;;
  esac
  if [[ -e "$candidate" ]]; then
    echo "include=$relative"
  else
    echo "skip_missing=$relative"
  fi
done

if [[ "$EXECUTE" -ne 1 ]]; then
  [[ -n "$RCLONE_DESTINATION" ]] && echo "would_upload_to=${RCLONE_DESTINATION%/}/$STAMP/"
  exit 0
fi

mkdir -p -- "$OUTPUT_DIR"
chmod 0700 "$OUTPUT_DIR"
stage="$(mktemp -d "$OUTPUT_DIR/.okra-backup-$STAMP.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT

rsync_excludes=(
  --exclude='*.env'
  --exclude='*.pem'
  --exclude='*.key'
  --exclude='*api_key*'
  --exclude='*cookie*'
  --exclude='*credentials*.json'
  --exclude='browser_profiles/'
  --exclude='alipay_screenshots/'
  --exclude='*.png'
  --exclude='*.jpg'
  --exclude='*.jpeg'
  --exclude='*.webp'
  --exclude='cache/'
  --exclude='temp/'
)

for relative in "${include_paths[@]}"; do
  [[ -e "$AGENT_HOME/$relative" ]] || continue
  rsync -aR "${rsync_excludes[@]}" "$AGENT_HOME/./$relative" "$stage/"
done

git_commit="unknown"
if git -C "$AGENT_HOME" rev-parse --verify HEAD >/dev/null 2>&1; then
  git_commit="$(git -C "$AGENT_HOME" rev-parse HEAD)"
fi
version="unknown"
if [[ -f "$AGENT_HOME/project.toml" ]]; then
  version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$AGENT_HOME/project.toml" | head -n 1)"
  [[ -n "$version" ]] || version="unknown"
fi

file_count="$(find "$stage" -type f | wc -l | tr -d ' ')"
total_bytes="$(du -sb "$stage" | awk '{print $1}')"
cat > "$stage/backup_metadata.env" <<EOF
schema_version=okra_backup.v1
created_at_utc=$STAMP
file_count_before_manifest=$file_count
total_bytes_before_manifest=$total_bytes
git_commit=$git_commit
okra_version=$version
EOF

(
  cd "$stage"
  find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256
)

archive="$OUTPUT_DIR/okra-$STAMP.tar.gz"
[[ ! -e "$archive" && ! -e "$archive.sha256" ]] || { echo "backup archive already exists: $archive" >&2; exit 1; }
partial="$archive.partial"
tar -C "$stage" -czf "$partial" .
mv -- "$partial" "$archive"
(
  cd "$OUTPUT_DIR"
  sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256"
)

if [[ -n "$RCLONE_DESTINATION" ]]; then
  command -v rclone >/dev/null 2>&1 || { echo "rclone is not installed" >&2; exit 1; }
  remote_prefix="${RCLONE_DESTINATION%/}/$STAMP"
  rclone copyto "$archive" "$remote_prefix/$(basename "$archive")"
  rclone copyto "$archive.sha256" "$remote_prefix/$(basename "$archive.sha256")"
fi

echo "backup_archive=$archive"
echo "backup_checksum=$archive.sha256"
