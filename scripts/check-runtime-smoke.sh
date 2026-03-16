#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/check-runtime-smoke.sh

Run a minimal zero-config smoke test against the current Sopify runtime bundle.
This script works both in the repository root and inside a vendored .sopify-runtime/ bundle.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

RUNTIME_ENTRY="$BUNDLE_ROOT/scripts/sopify_runtime.py"
if [[ ! -f "$RUNTIME_ENTRY" ]]; then
  echo "Missing runtime entry: $RUNTIME_ENTRY" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sopify-runtime-smoke.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

OUTPUT="$(
  python3 "$RUNTIME_ENTRY" \
    --workspace-root "$WORK_DIR" \
    --no-color \
    "重构数据库层"
)"

PLAN_DIR="$WORK_DIR/.sopify-skills/plan"
STATE_FILE="$WORK_DIR/.sopify-skills/state/current_plan.json"
REPLAY_DIR="$WORK_DIR/.sopify-skills/replay/sessions"
PROJECT_FILE="$WORK_DIR/.sopify-skills/project.md"
OVERVIEW_FILE="$WORK_DIR/.sopify-skills/wiki/overview.md"
PREFERENCES_FILE="$WORK_DIR/.sopify-skills/user/preferences.md"
HISTORY_INDEX="$WORK_DIR/.sopify-skills/history/index.md"

if [[ ! -d "$PLAN_DIR" ]]; then
  echo "Smoke check failed: missing plan directory: $PLAN_DIR" >&2
  exit 1
fi

if [[ ! -f "$STATE_FILE" ]]; then
  echo "Smoke check failed: missing state file: $STATE_FILE" >&2
  exit 1
fi

if [[ ! -d "$REPLAY_DIR" ]]; then
  echo "Smoke check failed: missing replay directory: $REPLAY_DIR" >&2
  exit 1
fi

for file in "$PROJECT_FILE" "$OVERVIEW_FILE" "$PREFERENCES_FILE" "$HISTORY_INDEX"; do
  if [[ ! -f "$file" ]]; then
    echo "Smoke check failed: missing KB bootstrap file: $file" >&2
    exit 1
  fi
done

if [[ "$OUTPUT" != *".sopify-skills/plan/"* ]]; then
  echo "Smoke check failed: runtime output did not include the plan path." >&2
  printf '%s\n' "$OUTPUT" >&2
  exit 1
fi

if [[ "$OUTPUT" != *".sopify-skills/project.md"* ]]; then
  echo "Smoke check failed: runtime output did not include KB bootstrap changes." >&2
  printf '%s\n' "$OUTPUT" >&2
  exit 1
fi

echo "Runtime smoke check passed:"
echo "  bundle root: $BUNDLE_ROOT"
echo "  workspace:   $WORK_DIR"
