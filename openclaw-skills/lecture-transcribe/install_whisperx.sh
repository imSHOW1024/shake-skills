#!/bin/bash
# lecture-transcribe v3.0.1 安裝腳本 (macOS Apple Silicon)
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[[ $(uname -m) != "arm64" ]] && error "僅適用 Apple Silicon"
command -v python3 &>/dev/null || error "找不到 python3"
command -v ffmpeg &>/dev/null || { warn "安裝 ffmpeg..."; brew install ffmpeg; }

VENV="$HOME/whisperx-env"
[ -d "$VENV" ] && { warn "$VENV 已存在"; read -p "重建? (y/N): " R; [[ "$R" =~ ^[Yy]$ ]] && rm -rf "$VENV"; }
[ ! -d "$VENV" ] && { info "建立 venv..."; python3 -m venv "$VENV"; }

source "$VENV/bin/activate"
pip install --upgrade pip setuptools wheel

info "安裝 mlx-whisper..."
pip install mlx-whisper

info "安裝 WhisperX (版本鎖定)..."
pip install "torch==2.2.2" "torchaudio==2.2.2"
pip install "whisperx==3.1.1"
pip install "pyannote.audio==3.1.1"

info "安裝 Pipeline 依賴..."
pip install notion-client pyyaml huggingface-hub anthropic

# --- PyTorch 2.6 相容性 (pyannote weights_only 問題) ---
info "設定 TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD..."
ZSHRC="$HOME/.zshrc"
if ! grep -q "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD" "$ZSHRC" 2>/dev/null; then
    echo '' >> "$ZSHRC"
    echo '# PyTorch 2.6 weights_only 相容性 (pyannote 需要)' >> "$ZSHRC"
    echo 'export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1' >> "$ZSHRC"
    info "已寫入 ~/.zshrc"
else
    info "~/.zshrc 已有此設定"
fi
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

# --- 驗證 ---
python3 -c "
import mlx_whisper; print('✅ mlx-whisper')
import torch, whisperx; print(f'✅ whisperx={whisperx.__version__} torch={torch.__version__}')
try:
    import pyannote.audio; print(f'✅ pyannote={pyannote.audio.__version__}')
except: print('⚠️  pyannote 有問題')
import notion_client; print('✅ notion-client')
"

echo ""
echo "========================================"
echo "  Diarization 需要 HF_TOKEN"
echo "  https://huggingface.co/settings/tokens"
echo "  Accept: pyannote/segmentation-3.0"
echo "         pyannote/speaker-diarization-3.1"
echo "========================================"

info "執行健檢..."
bash "$(dirname "$0")/check_env.sh" || true
info "安裝完成! 🎉"
