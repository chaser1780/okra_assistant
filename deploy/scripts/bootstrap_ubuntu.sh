#!/usr/bin/env bash
set -euo pipefail

APP_HOME="/opt/okra_assistant"
SERVICE_USER="okra"
DRY_RUN=1
WITH_NODE=0
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

usage() {
  cat <<'EOF'
Usage: bootstrap_ubuntu.sh [--execute] [--with-node] [--source-dir PATH]

Prepares /opt/okra_assistant on Ubuntu. The default is a dry run. This script
does not create Cloudflare credentials, replace env placeholders, open firewall
ports, or enable services.
EOF
}

print_command() {
  printf 'DRY-RUN:'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_command "$@"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      DRY_RUN=0
      shift
      ;;
    --with-node)
      WITH_NODE=1
      shift
      ;;
    --source-dir)
      [[ $# -ge 2 ]] || { echo "--source-dir requires a value" >&2; exit 2; }
      SOURCE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SOURCE_DIR="$(realpath -e -- "$SOURCE_DIR")"
[[ "$SOURCE_DIR" != "/" ]] || { echo "source directory cannot be /" >&2; exit 2; }
[[ -f "$SOURCE_DIR/requirements.txt" ]] || { echo "requirements.txt not found in source directory" >&2; exit 2; }
[[ -d "$SOURCE_DIR/deploy/systemd" ]] || { echo "deploy templates not found in source directory" >&2; exit 2; }
[[ "$APP_HOME" == /opt/* && "$APP_HOME" != "/opt/" ]] || { echo "unsafe APP_HOME" >&2; exit 2; }

if [[ "$DRY_RUN" -eq 0 && "${EUID}" -ne 0 ]]; then
  echo "--execute must run as root" >&2
  exit 1
fi

packages=(python3 python3-venv python3-pip git curl ca-certificates rsync rclone jq util-linux)
if [[ "$WITH_NODE" -eq 1 ]]; then
  packages+=(nodejs npm)
fi

run apt-get update
run apt-get install -y --no-install-recommends "${packages[@]}"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  run useradd --system --create-home --home-dir /var/lib/okra --shell /usr/sbin/nologin "$SERVICE_USER"
fi

run install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP_HOME"
if [[ "$SOURCE_DIR" != "$APP_HOME" ]]; then
  rsync_args=(
    -a
    --exclude=.git/
    --exclude=.venv/
    --exclude=node_modules/
    --exclude=frontend/node_modules/
    --exclude=frontend/src-tauri/target/
    --exclude=db/
    --exclude=raw/
    --exclude=reports/daily/
    --exclude=logs/
    --exclude=cache/
    --exclude=temp/
    --exclude='config/*key*.txt'
    --exclude='config/*cookie*.txt'
    "$SOURCE_DIR/"
    "$APP_HOME/"
  )
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_command rsync "${rsync_args[@]}"
  else
    rsync "${rsync_args[@]}"
  fi
fi

run chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_HOME"
run chmod 0750 "$APP_HOME"/deploy/scripts/*.sh
run runuser -u "$SERVICE_USER" -- python3 -m venv "$APP_HOME/.venv"
run runuser -u "$SERVICE_USER" -- "$APP_HOME/.venv/bin/python" -m pip install --upgrade pip
run runuser -u "$SERVICE_USER" -- "$APP_HOME/.venv/bin/python" -m pip install -r "$APP_HOME/requirements.txt"

if [[ "$WITH_NODE" -eq 1 ]]; then
  run runuser -u "$SERVICE_USER" -- npm --prefix "$APP_HOME/frontend" ci
  run runuser -u "$SERVICE_USER" -- npm --prefix "$APP_HOME/frontend" run build
fi

run install -d -m 0750 /etc/okra
if [[ ! -e /etc/okra/okra.env ]]; then
  run install -o root -g "$SERVICE_USER" -m 0640 "$APP_HOME/deploy/env/okra.env.example" /etc/okra/okra.env
else
  echo "preserving existing /etc/okra/okra.env"
fi

for unit in okra-api.service okra-daily.service okra-daily.timer okra-realtime.service okra-realtime.timer; do
  run install -o root -g root -m 0644 "$APP_HOME/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done
run systemctl daemon-reload

cat <<'EOF'

Bootstrap preparation complete.
Before enabling anything:
  1. Replace every placeholder in /etc/okra/okra.env and keep mode 0640 or stricter.
  2. Install/configure cloudflared and optionally Caddy from vendor-supported repositories.
  3. Validate units with systemd-analyze verify and timers with systemd-analyze calendar.
  4. Start okra-api, run deploy/scripts/healthcheck.sh, then enable timers one at a time.
EOF
