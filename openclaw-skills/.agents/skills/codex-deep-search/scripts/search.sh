#!/usr/bin/env bash
# Deep search via Codex CLI with dispatch pattern (background + Telegram callback)
set -euo pipefail

# --- macOS-friendly defaults ---
WORKDIR="$HOME/.openclaw/workspace"
RESULT_DIR="$WORKDIR/codex-search-results"  # keep inside workspace so Codex sandbox can write
OPENCLAW_BIN="/opt/homebrew/bin/openclaw"
CODEX_BIN="${CODEX_BIN:-/opt/homebrew/bin/codex}"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

# Defaults
PROMPT=""
OUTPUT=""
MODEL="gpt-5.3-codex"
SANDBOX="workspace-write"
TIMEOUT=120
TELEGRAM_GROUP=""
TASK_NAME="search-$(date +%s)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt) PROMPT="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    --telegram-group) TELEGRAM_GROUP="$2"; shift 2;;
    --task-name) TASK_NAME="$2"; shift 2;;
    *) echo "Unknown flag: $1" >&2; exit 1;;
  esac
done

if [[ -z "$PROMPT" ]]; then
  echo "ERROR: --prompt is required" >&2
  exit 1
fi

mkdir -p "$RESULT_DIR"

# Default output path
if [[ -z "$OUTPUT" ]]; then
  OUTPUT="${RESULT_DIR}/${TASK_NAME}.md"
fi

# Write task metadata
STARTED_AT="$(date -Iseconds)"
jq -n \
  --arg name "$TASK_NAME" \
  --arg prompt "$PROMPT" \
  --arg output "$OUTPUT" \
  --arg ts "$STARTED_AT" \
  '{task_name: $name, prompt: $prompt, output: $output, started_at: $ts, status: "running"}' \
  > "${RESULT_DIR}/latest-meta.json"

SEARCH_INSTRUCTION="You are a research assistant. Search the web for the following query.

CRITICAL RULES:
1. Write findings to $OUTPUT INCREMENTALLY — after EACH search, append what you found immediately. Do NOT wait until the end.
2. Start the file with a title and query, then append sections as you discover them.
3. Keep searches focused — max 8 web searches. Synthesize what you have, don't over-research.
4. Include source URLs inline.
5. End with a brief summary section.

Query: $PROMPT

Start by writing the file header NOW, then search and append."

echo "[codex-deep-search] Task: $TASK_NAME"
echo "[codex-deep-search] Output: $OUTPUT"
echo "[codex-deep-search] Model: $MODEL | Reasoning: low | Timeout: ${TIMEOUT}s"

# Pre-create output file
cat > "$OUTPUT" <<OUTEOF
# Deep Search Report
**Query:** $PROMPT
**Status:** In progress...
---
OUTEOF

TIMEOUT_BIN=""
if command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
elif command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
fi

set +e
CMD=("$CODEX_BIN" exec \
  --skip-git-repo-check \
  -C "$WORKDIR" \
  --model "$MODEL" \
  --full-auto \
  --sandbox "$SANDBOX" \
  -c 'model_reasoning_effort="low"' \
  "$SEARCH_INSTRUCTION")

if [[ -n "$TIMEOUT_BIN" ]]; then
  "$TIMEOUT_BIN" "${TIMEOUT}" "${CMD[@]}" 2>&1 | tee "${RESULT_DIR}/task-output.txt"
  EXIT_CODE=${PIPESTATUS[0]}
else
  "${CMD[@]}" 2>&1 | tee "${RESULT_DIR}/task-output.txt"
  EXIT_CODE=${PIPESTATUS[0]}
fi
set -e

# Append completion marker
if [[ -f "$OUTPUT" ]]; then
  echo -e "\n---\n_Search completed at $(date -u)_" >> "$OUTPUT"
fi

LINES=$(wc -l < "$OUTPUT" 2>/dev/null || echo 0)
COMPLETED_AT="$(date -Iseconds)"

# Calculate duration (portable)
START_TS=$(python3 - <<PY
import datetime
print(int(datetime.datetime.fromisoformat("$STARTED_AT").timestamp()))
PY
)
END_TS=$(date +%s)
ELAPSED=$(( END_TS - START_TS ))
MINS=$(( ELAPSED / 60 ))
SECS=$(( ELAPSED % 60 ))
DURATION="${MINS}m${SECS}s"

# Update metadata
jq -n \
  --arg name "$TASK_NAME" \
  --arg prompt "$PROMPT" \
  --arg output "$OUTPUT" \
  --arg started "$STARTED_AT" \
  --arg completed "$COMPLETED_AT" \
  --arg duration "$DURATION" \
  --arg lines "$LINES" \
  --argjson exit_code "$EXIT_CODE" \
  '{task_name: $name, prompt: $prompt, output: $output, started_at: $started, completed_at: $completed, duration: $duration, lines: ($lines|tonumber), exit_code: $exit_code, status: (if $exit_code == 0 then "done" elif $exit_code == 124 then "timeout" else "failed" end)}' \
  > "${RESULT_DIR}/latest-meta.json"

echo "[codex-deep-search] Done (${DURATION}, exit=${EXIT_CODE}, ${LINES} lines)"

echo "[codex-deep-search] Results folder: $RESULT_DIR" >&2

# ---- Wake via /hooks/wake (optional) ----
HOOK_TOKEN=""
if [[ -f "$OPENCLAW_CONFIG" ]]; then
  HOOK_TOKEN=$(jq -r '.hooks.token // ""' "$OPENCLAW_CONFIG" 2>/dev/null || echo "")
fi

if [[ -n "$HOOK_TOKEN" ]]; then
  GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
  WAKE_TEXT="[DEEP_SEARCH_DONE] task=${TASK_NAME} output=${OUTPUT} lines=${LINES} duration=${DURATION} status=$(jq -r '.status' "${RESULT_DIR}/latest-meta.json" 2>/dev/null)"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "http://localhost:${GATEWAY_PORT}/hooks/wake" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${HOOK_TOKEN}" \
    -d "{\"text\":\"${WAKE_TEXT}\",\"mode\":\"now\"}" 2>/dev/null)
  echo "[codex-deep-search] Wake sent (HTTP ${HTTP_CODE})"
else
  echo "[codex-deep-search] No hook token, skipping wake" >&2
fi
