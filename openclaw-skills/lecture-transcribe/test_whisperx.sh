#!/bin/bash
# test_whisperx.sh — 轉錄 + diarization 測試
set -e
VENV="$HOME/whisperx-env"
AUDIO="${1:-}"
[ -z "$AUDIO" ] && { echo "用法: bash test_whisperx.sh <音訊檔>"; exit 1; }
[ ! -f "$AUDIO" ] && { echo "❌ 找不到: $AUDIO"; exit 1; }
source "$VENV/bin/activate"

echo "=== 轉錄測試 ==="
echo "音訊: $AUDIO"

python3 << PYEOF
import sys, os, time, json

audio = "$AUDIO"

print("\n🔥 Test 1: mlx-whisper (large-v3)")
try:
    import mlx_whisper
    t0 = time.time()
    r = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-large-v3-mlx", word_timestamps=True)
    e = time.time() - t0
    segs = r.get("segments", [])
    dur = segs[-1]["end"] if segs else 0
    print(f"   ✅ {e:.1f}s | {len(segs)}段 | {dur:.0f}s音訊 | {dur/e:.1f}x realtime")
    for s in segs[:3]:
        print(f"   [{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()[:60]}")
except Exception as ex:
    print(f"   ❌ {ex}")

print("\n📦 Test 2: WhisperX (base, 快速驗證)")
try:
    import whisperx
    t0 = time.time()
    m = whisperx.load_model("base", "cpu", compute_type="int8")
    r = m.transcribe(audio, batch_size=4)
    print(f"   ✅ {time.time()-t0:.1f}s | {len(r.get('segments',[]))}段")
except Exception as ex:
    print(f"   ❌ {ex}")

print("\n🎤 Test 3: pyannote diarization")
hf = os.environ.get("HF_TOKEN", "")
if not hf:
    print("   ⏭️  HF_TOKEN 未設定")
else:
    try:
        from pyannote.audio import Pipeline
        t0 = time.time()
        p = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf)
        d = p(audio)
        spks = set(s for _, _, s in d.itertracks(yield_label=True))
        print(f"   ✅ {time.time()-t0:.1f}s | {len(spks)} speakers")
    except Exception as ex:
        print(f"   ❌ {ex}")

print("\n✅ 測試結束")
PYEOF
