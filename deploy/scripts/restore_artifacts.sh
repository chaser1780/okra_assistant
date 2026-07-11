#!/usr/bin/env bash
set -euo pipefail

ARCHIVE=""
CHECKSUM_FILE=""
TARGET_HOME="/opt/okra_restore_test"
ACTIVE_HOME="${FUND_AGENT_HOME:-/opt/okra_assistant}"
OWNER=""
EXECUTE=0
CONFIRM_RESTORE=0

usage() {
  cat <<'EOF'
Usage: restore_artifacts.sh --archive PATH [--checksum PATH]
                            [--target-home PATH] [--owner USER]
                            [--execute --confirm-restore]

The default validates the archive without restoring it. Execute mode only
writes to an absent or empty target that is separate from FUND_AGENT_HOME.
Existing files are never removed or overwritten by this script.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive)
      [[ $# -ge 2 ]] || { echo "--archive requires a value" >&2; exit 2; }
      ARCHIVE="$2"
      shift 2
      ;;
    --checksum)
      [[ $# -ge 2 ]] || { echo "--checksum requires a value" >&2; exit 2; }
      CHECKSUM_FILE="$2"
      shift 2
      ;;
    --target-home)
      [[ $# -ge 2 ]] || { echo "--target-home requires a value" >&2; exit 2; }
      TARGET_HOME="$2"
      shift 2
      ;;
    --owner)
      [[ $# -ge 2 ]] || { echo "--owner requires a value" >&2; exit 2; }
      OWNER="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --confirm-restore)
      CONFIRM_RESTORE=1
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

[[ -n "$ARCHIVE" ]] || { echo "--archive is required" >&2; exit 2; }
ARCHIVE="$(realpath -e -- "$ARCHIVE")"
[[ -f "$ARCHIVE" && "$ARCHIVE" == *.tar.gz ]] || { echo "archive must be an existing .tar.gz file" >&2; exit 2; }
if [[ -z "$CHECKSUM_FILE" ]]; then
  CHECKSUM_FILE="$ARCHIVE.sha256"
fi
CHECKSUM_FILE="$(realpath -e -- "$CHECKSUM_FILE")"
[[ -f "$CHECKSUM_FILE" ]] || { echo "checksum file not found" >&2; exit 2; }
TARGET_HOME="$(realpath -m -- "$TARGET_HOME")"
ACTIVE_HOME="$(realpath -m -- "$ACTIVE_HOME")"
[[ "$TARGET_HOME" = /* && "$TARGET_HOME" != "/" ]] || { echo "target home must be a safe absolute path" >&2; exit 2; }
case "$ACTIVE_HOME" in
  "$TARGET_HOME"|"$TARGET_HOME"/*) echo "target cannot be the active home or its ancestor" >&2; exit 2 ;;
esac
case "$TARGET_HOME" in
  "$ACTIVE_HOME"/*) echo "target cannot be inside the active home" >&2; exit 2 ;;
esac
if [[ -n "$OWNER" ]]; then
  [[ "$OWNER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "invalid owner name" >&2; exit 2; }
  id "$OWNER" >/dev/null 2>&1 || { echo "owner does not exist: $OWNER" >&2; exit 2; }
fi
if [[ "$EXECUTE" -eq 1 && "$CONFIRM_RESTORE" -ne 1 ]]; then
  echo "--execute requires --confirm-restore" >&2
  exit 2
fi
if [[ -e "$TARGET_HOME" && -n "$(find "$TARGET_HOME" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "target home must be absent or empty: $TARGET_HOME" >&2
  exit 2
fi

expected_hash="$(awk 'NR == 1 {print $1}' "$CHECKSUM_FILE")"
[[ "$expected_hash" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "invalid external checksum file" >&2; exit 2; }
actual_hash="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ "${actual_hash,,}" == "${expected_hash,,}" ]] || { echo "archive checksum mismatch" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
python3 - "$ARCHIVE" "$stage" <<'PY'
import inspect
import pathlib
import sys
import tarfile

archive = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2]).resolve()
allowed = {"db", "raw", "reports", "config", "deploy", "project.toml", "requirements.txt", "backup_metadata.env", "manifest.sha256"}
with tarfile.open(archive, "r:gz") as handle:
    members = handle.getmembers()
    if not members:
        raise SystemExit("backup archive is empty")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        parts = tuple(part for part in path.parts if part not in {"", "."})
        if not parts and member.isdir():
            continue
        if not parts or path.is_absolute() or ".." in parts:
            raise SystemExit(f"unsafe archive member path: {member.name}")
        if parts[0] not in allowed:
            raise SystemExit(f"unexpected archive top-level path: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"unsupported archive member type: {member.name}")
        destination = (target / pathlib.Path(*parts)).resolve()
        if target != destination and target not in destination.parents:
            raise SystemExit(f"archive member escapes staging directory: {member.name}")
    kwargs = {"filter": "data"} if "filter" in inspect.signature(handle.extractall).parameters else {}
    handle.extractall(target, **kwargs)
PY

[[ -f "$stage/manifest.sha256" ]] || { echo "archive manifest.sha256 is missing" >&2; exit 1; }
(
  cd "$stage"
  sha256sum --check --strict manifest.sha256
)

if find "$stage" -type f \( -iname '*.env' -o -iname '*.pem' -o -iname '*.key' -o -iname '*api_key*' -o -iname '*cookie*' -o -iname '*credentials*.json' \) ! -path "$stage/backup_metadata.env" ! -path '*/deploy/env/*.env.example' -print -quit | grep -q .; then
  echo "archive contains a forbidden secret-like file" >&2
  exit 1
fi

echo "restore_validation=ok"
echo "archive=$ARCHIVE"
echo "target_home=$TARGET_HOME"
if [[ "$EXECUTE" -ne 1 ]]; then
  echo "restore_mode=dry-run"
  exit 0
fi

mkdir -p -- "$TARGET_HOME"
chmod 0750 "$TARGET_HOME"
cp -a "$stage/." "$TARGET_HOME/"
if [[ -n "$OWNER" ]]; then
  chown -R "$OWNER:$OWNER" "$TARGET_HOME"
fi
echo "restore_mode=execute"
echo "restored_home=$TARGET_HOME"
