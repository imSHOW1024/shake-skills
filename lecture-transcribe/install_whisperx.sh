#!/bin/bash
# lecture-transcribe v3.1 安裝腳本 (macOS Apple Silicon)
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
PYTHON_BIN="${LECTURE_PYTHON_BIN:-$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3 || true)}"
VENV="${LECTURE_VENV:-$HOME/whisperx-env-312}"

[[ $(uname -m) != "arm64" ]] && error "僅適用 Apple Silicon"
[[ -n "$PYTHON_BIN" ]] || error "找不到可用的 Python（建議安裝 python3.12 或 python3.11）"
command -v ffmpeg &>/dev/null || { warn "安裝 ffmpeg..."; brew install ffmpeg; }

PY_VER="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PY_VER" in
  3.11|3.12) ;;
  *) error "目前 Python 版本為 $PY_VER；lecture-transcribe 建議使用 3.11 或 3.12" ;;
esac

info "使用 Python: $PYTHON_BIN ($PY_VER)"
info "目標 venv: $VENV"

if [ -d "$VENV" ]; then
    warn "$VENV 已存在"
    read -p "重建? (y/N): " R
    [[ "$R" =~ ^[Yy]$ ]] && rm -rf "$VENV"
fi
[ ! -d "$VENV" ] && { info "建立 venv..."; "$PYTHON_BIN" -m venv "$VENV"; }

source "$VENV/bin/activate"
python -m pip install --upgrade pip setuptools wheel

info "安裝 mlx-whisper..."
python -m pip install mlx-whisper

info "安裝 WhisperX (版本鎖定)..."
python -m pip install "torch==2.2.2" "torchaudio==2.2.2"
python -m pip install "whisperx==3.1.1"
python -m pip install "pyannote.audio==3.1.1"
python -m pip install openai-whisper

info "安裝 Pipeline 依賴..."
python -m pip install -r "$REQUIREMENTS_FILE"

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
python -c "
import sys
print(f'✅ python={sys.version.split()[0]}')
import mlx_whisper; print('✅ mlx-whisper')
import torch, whisperx; print(f'✅ whisperx={whisperx.__version__} torch={torch.__version__}')
try:
    import pyannote.audio; print(f'✅ pyannote={pyannote.audio.__version__}')
except Exception as ex: print(f'⚠️  pyannote 有問題: {ex}')
import notion_client; print('✅ notion-client')
import yaml; print('✅ pyyaml')
import lecture_pipeline; print('✅ lecture_pipeline import smoke test')
"

echo ""
echo "========================================"
echo "  Diarization 需要 HF_TOKEN"
echo "  https://huggingface.co/settings/tokens"
echo "  Accept: pyannote/segmentation-3.0"
echo "         pyannote/speaker-diarization-3.1"
echo "========================================"

info "執行健檢..."
LECTURE_VENV="$VENV" bash "$SCRIPT_DIR/check_env.sh" || true
info "安裝完成! 🎉"
