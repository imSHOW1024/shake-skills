#!/bin/bash
# check_env.sh — 環境健檢
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo -e "  ${GREEN}✅${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}❌${NC} $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}⚠️${NC} $1"; ((WARN++)); }

VENV="$HOME/whisperx-env"
echo "=== Lecture-Transcribe v3 環境健檢 ==="

echo ""; echo "📦 虛擬環境"
[ -d "$VENV" ] && { ok "whisperx-env"; source "$VENV/bin/activate"; } || fail "whisperx-env 不存在"

echo ""; echo "🔧 系統"
command -v ffmpeg &>/dev/null && ok "ffmpeg" || fail "ffmpeg"
command -v ffprobe &>/dev/null && ok "ffprobe" || fail "ffprobe"

echo ""; echo "🐍 Python"
python3 -c "import mlx_whisper" 2>/dev/null && ok "mlx-whisper (主力)" || fail "mlx-whisper"
python3 -c "import torch, whisperx" 2>/dev/null && ok "WhisperX (備援)" || warn "WhisperX"
python3 -c "import pyannote.audio" 2>/dev/null && ok "pyannote" || warn "pyannote"
python3 -c "import notion_client" 2>/dev/null && ok "notion-client" || fail "notion-client"
python3 -c "import yaml" 2>/dev/null && ok "pyyaml" || fail "pyyaml"

echo ""; echo "🔑 環境變數"
[ -n "$HF_TOKEN" ] && ok "HF_TOKEN" || warn "HF_TOKEN 未設定"
[ -n "$NOTION_API_KEY" ] && ok "NOTION_API_KEY" || fail "NOTION_API_KEY 未設定"

echo ""; echo "⚡ 硬體"
MEM=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f", $1/1024/1024/1024}')
echo "  記憶體: ${MEM:-?}GB"
[[ "${MEM:-0}" -ge 32 ]] && ok "large-v3 OK" || warn "建議 medium"

echo ""
echo "=== ✅:$PASS ❌:$FAIL ⚠️:$WARN ==="
[ $FAIL -gt 0 ] && exit 1 || exit 0
