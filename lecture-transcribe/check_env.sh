#!/bin/bash
# lecture-transcribe v3.1 環境健檢
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo -e "  ${GREEN}✅${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}❌${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}⚠️${NC} $1"; WARN=$((WARN+1)); }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${LECTURE_VENV:-$HOME/whisperx-env-312}"

echo "=== lecture-transcribe v3.1 健檢 ==="

echo ""; echo "📦 環境"
if [ -d "$VENV" ]; then
  ok "venv: $VENV"
  source "$VENV/bin/activate"
else
  fail "venv 不存在: $VENV"
fi
command -v ffmpeg &>/dev/null && ok "ffmpeg" || fail "ffmpeg"
command -v ffprobe &>/dev/null && ok "ffprobe" || fail "ffprobe"

PY_VER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)"
if [[ "$PY_VER" == 3.11.* || "$PY_VER" == 3.12.* ]]; then
  ok "python=$PY_VER"
else
  fail "python 版本不符：$PY_VER（建議 3.11 或 3.12）"
fi

echo ""; echo "🐍 套件"
python -c "import mlx_whisper" 2>/dev/null        && ok "mlx-whisper (主力)" || fail "mlx-whisper"
python -c "import whisperx" 2>/dev/null            && ok "whisperx (備援)"   || warn "whisperx"
python -c "import pyannote.audio" 2>/dev/null      && ok "pyannote"          || warn "pyannote"
python -c "import notion_client" 2>/dev/null       && ok "notion-client"     || fail "notion-client"
python -c "import yaml" 2>/dev/null                && ok "pyyaml"            || fail "pyyaml"
python -c "import anthropic" 2>/dev/null           && ok "anthropic SDK"     || warn "anthropic"
python -c "import lecture_pipeline" 2>/dev/null    && ok "lecture_pipeline import smoke test" || fail "lecture_pipeline import"
command -v whisper >/dev/null 2>&1                  && ok "openai-whisper CLI" || warn "openai-whisper CLI"
command -v whisperx >/dev/null 2>&1                 && ok "whisperx CLI" || warn "whisperx CLI"

echo ""; echo "🔑 環境變數"
[ -n "${NOTION_API_KEY:-}" ]    && ok "NOTION_API_KEY"    || fail "NOTION_API_KEY"
[ -n "${HF_TOKEN:-}" ]          && ok "HF_TOKEN"          || warn "HF_TOKEN (diarization)"
[ -n "${ANTHROPIC_API_KEY:-}" ] && ok "ANTHROPIC_API_KEY"  || warn "ANTHROPIC_API_KEY (LLM)"
[ "${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD:-}" = "1" ] \
    && ok "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" \
    || warn "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD 未設定 (pyannote 可能報錯)"

echo ""; echo "⚡ 硬體"
MEM=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f",$1/1073741824}')
echo "  RAM: ${MEM:-?}GB"
[[ "${MEM:-0}" -ge 32 ]] && ok "large-v3 OK" || warn "建議 medium"

echo ""
echo "=== ✅:$PASS ❌:$FAIL ⚠️:$WARN ==="
[ $FAIL -gt 0 ] && exit 1 || exit 0
