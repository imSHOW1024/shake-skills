#!/usr/bin/env bash
# lme_browser_eval.sh  —  Wraps `openclaw browser evaluate` via exec (not Python subprocess).
set -euo pipefail

LME_BASE_URL="${LME_BASE_URL:-https://www.lme.com}"
MAX_RETRIES=3
RETRY_DELAY=3
TARGET_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --datasource-id)  DATASOURCE_ID="$2";  shift 2 ;;
    --start-date)     START_DATE="$2";     shift 2 ;;
    --end-date)       END_DATE="$2";       shift 2 ;;
    --browser-profile) BROWSER_PROFILE="$2"; shift 2 ;;
    --target-id)      TARGET_ID="$2";       shift 2 ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 1 ;;
  esac
done

required_vars=(DATASOURCE_ID START_DATE END_DATE)
for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then echo "ERROR: --$v is required" >&2; exit 1; fi
done

RELATIVE_URL="/api/trading-data/chart-data?datasourceId=${DATASOURCE_ID}&startDate=${START_DATE}&endDate=${END_DATE}"

_last_json() {
  python3 -c "
import sys, json
text = sys.stdin.read()
idx = text.rfind(chr(10)+chr(123))
if idx == -1: idx = text.find(chr(123))
if idx == -1: exit(1)
print(text[idx:])
"
}

if [[ -z "$TARGET_ID" ]]; then
  for ((i=1; i<=MAX_RETRIES; i++)); do
    PAGE_OUT=$(openclaw browser --browser-profile openclaw --json open "${LME_BASE_URL}/metals/non-ferrous/lme-aluminium" 2>/dev/null) && break
    if [[ $i -lt MAX_RETRIES ]]; then
      echo "WARN: page open attempt $i failed, retrying in ${RETRY_DELAY}s..." >&2
      sleep "$RETRY_DELAY"
    fi
  done
  if [[ -z "$PAGE_OUT" ]]; then
    echo "ERROR: failed to open LME page after $MAX_RETRIES attempts" >&2; exit 1; fi
  LAST_JSON=$(echo "$PAGE_OUT" | _last_json) || {
    echo "ERROR: could not parse targetId from page open" >&2; exit 1; }
  TARGET_ID=$(echo "$LAST_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("targetId",""))' 2>/dev/null)
  if [[ -z "$TARGET_ID" ]]; then
    echo "ERROR: targetId missing in page open response" >&2; exit 1; fi
fi

EVAL_OUT=""
for ((i=1; i<=MAX_RETRIES; i++)); do
  EVAL_OUT=$(openclaw browser --browser-profile openclaw --json evaluate   --target-id "$TARGET_ID"   --fn "() => fetch('${RELATIVE_URL}').then(async r => { const t = await r.text(); if(!r.ok) throw Error('HTTP '+r.status); return JSON.parse(t); })"   2>/dev/null) && break
  if [[ $i -lt MAX_RETRIES ]]; then
    echo "WARN: evaluate attempt $i failed, retrying in ${RETRY_DELAY}s..." >&2
    sleep "$RETRY_DELAY"
  fi
done
if [[ -z "$EVAL_OUT" ]]; then
  echo "ERROR: openclaw browser evaluate failed after $MAX_RETRIES attempts" >&2; exit 1; fi

RESULT_JSON=$(echo "$EVAL_OUT" | _last_json) || {
  echo "ERROR: no JSON from evaluate output" >&2; exit 1; }

# Strip openclaw wrapper, output raw LME payload
echo "$RESULT_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('result',d)))"
