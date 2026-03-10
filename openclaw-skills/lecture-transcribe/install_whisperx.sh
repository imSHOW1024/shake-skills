#!/bin/bash
# install_whisperx.sh v3 — mlx-whisper + WhisperX (版本鎖定) + pyannote
set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[[ $(uname -m) != "arm64" ]] && error "僅適用 Apple Silicon"
command -v python3 &>/dev/null || error "找不到 python3"
command -v ffmpeg &>/dev/null || { warn "安裝 ffmpeg..."; brew install ffmpeg; }

VENV="$HOME/whisperx-env"
if [ -d "$VENV" ]; then
    warn "虛擬環境已存在: $VENV"
    read -p "刪除重建? (y/N): " R
    [[ "$R" =~ ^[Yy]$ ]] && rm -rf "$VENV"
fi
[ ! -d "$VENV" ] && { info "建立虛擬環境..."; python3 -m venv "$VENV"; }
source "$VENV/bin/activate"
pip install --upgrade pip setuptools wheel

info "===== mlx-whisper (主力) ====="
pip install mlx-whisper

info "===== WhisperX + pyannote (備援, 版本鎖定) ====="
pip install "torch==2.2.2" "torchaudio==2.2.2"
pip install "whisperx==3.1.1"
pip install "pyannote.audio==3.1.1"

info "===== Pipeline 依賴 ====="
pip install notion-client pyyaml huggingface-hub

echo ""
echo "============================================================"
echo "  Diarization 需要 HuggingFace Token"
echo "  1. https://huggingface.co/settings/tokens"
echo "  2. Accept: pyannote/segmentation-3.0"
echo "     Accept: pyannote/speaker-diarization-3.1"
echo "  3. 設定 HF_TOKEN 到 OpenClaw 服務環境"
echo "============================================================"

info "===== 環境健檢 ====="
bash "$(dirname "$0")/check_env.sh" || true
info "安裝完成! 🎉"
