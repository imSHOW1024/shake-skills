#!/bin/bash
# lecture-transcribe v3.0.1 環境健檢

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo -e "  ${GREEN}✅${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}❌${NC} $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}⚠️${NC} $1"; ((WARN++)); }

VENV="$HOME/whisperx-env"
echo "=== lecture-transcribe v3.0.1 健檢 ==="

echo ""; echo "📦 環境"
[ -d "$VENV" ] && { ok "venv"; source "$VENV/bin/activate"; } || fail "venv 不存在"
command -v ffmpeg &>/dev/null && ok "ffmpeg" || fail "ffmpeg"
command -v ffprobe &>/dev/null && ok "ffprobe" || fail "ffprobe"

echo ""; echo "🐍 套件"
python3 -c "import mlx_whisper" 2>/dev/null        && ok "mlx-whisper (主力)" || fail "mlx-whisper"
python3 -c "import whisperx" 2>/dev/null            && ok "whisperx (備援)"   || warn "whisperx"
python3 -c "import pyannote.audio" 2>/dev/null      && ok "pyannote"          || warn "pyannote"
python3 -c "import notion_client" 2>/dev/null       && ok "notion-client"     || fail "notion-client"
python3 -c "import yaml" 2>/dev/null                && ok "pyyaml"            || fail "pyyaml"
python3 -c "import anthropic" 2>/dev/null           && ok "anthropic SDK"     || warn "anthropic"

echo ""; echo "🔑 環境變數"
[ -n "$NOTION_API_KEY" ]    && ok "NOTION_API_KEY"    || fail "NOTION_API_KEY"
[ -n "$HF_TOKEN" ]          && ok "HF_TOKEN"          || warn "HF_TOKEN (diarization)"
[ -n "$ANTHROPIC_API_KEY" ] && ok "ANTHROPIC_API_KEY"  || warn "ANTHROPIC_API_KEY (LLM)"
[ "$TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" = "1" ] \
    && ok "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" \
    || warn "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD 未設定 (pyannote 可能報錯)"

echo ""; echo "⚡ 硬體"
MEM=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f",$1/1073741824}')
echo "  RAM: ${MEM:-?}GB"
[[ "${MEM:-0}" -ge 32 ]] && ok "large-v3 OK" || warn "建議 medium"

echo ""
echo "=== ✅:$PASS ❌:$FAIL ⚠️:$WARN ==="
[ $FAIL -gt 0 ] && exit 1 || exit 0
