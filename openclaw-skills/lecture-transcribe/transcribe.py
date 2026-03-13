"""
transcribe.py — 轉錄引擎 + Diarization + 音訊處理

三層 fallback: mlx-whisper → WhisperX → openai-whisper CLI
Diarization: pyannote standalone (獨立於轉錄引擎)
音訊處理: ffmpeg 切割 / 合併
"""

import os
import re
import json
import time
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

CONFIG = {
    "mlx_whisper": {"model": "large-v3"},
    "whisperx": {
        "model_size": "large-v3",
        "device": "cpu",
        "compute_type": "int8",
        "batch_size": 8,
        "language": None,
    },
    "diarization": {"min_speakers": 1, "max_speakers": 5},
}


# ============================================================
# 轉錄 (三層 Fallback)
# ============================================================

def transcribe_audio(
    audio_path: str,
    progress_cb: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Transcribe audio with engine fallback.

    `progress_cb` is the preferred arg name (used by lecture_pipeline.py).
    `progress_callback` is kept for backward compatibility.
    """
    if progress_cb is None:
        progress_cb = progress_callback
    engines = [
        ("mlx-whisper", _transcribe_mlx),
        ("whisperx", _transcribe_whisperx),
        ("openai-whisper", _transcribe_openai_cli),
    ]

    last_error = None
    for name, fn in engines:
        try:
            if progress_cb:
                progress_cb(f"🔄 嘗試 {name}...")
            t0 = time.time()
            result = fn(audio_path)
            elapsed = time.time() - t0
            result["engine_used"] = name
            result["transcribe_time_sec"] = elapsed
            logger.info(f"{name} OK ({elapsed:.1f}s)")
            if progress_cb:
                progress_cb(f"✅ {name} 完成 ({elapsed:.0f}s)")
            return result
        except Exception as e:
            last_error = e
            logger.warning(f"{name} 失敗: {e}")
            if progress_cb:
                progress_cb(f"⚠️ {name} 失敗，嘗試下一個...")

    raise RuntimeError(f"所有引擎失敗: {last_error}")


def _transcribe_mlx(audio_path: str) -> dict:
    import mlx_whisper
    model = CONFIG["mlx_whisper"]["model"]
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=f"mlx-community/whisper-{model}-mlx",
        word_timestamps=True,
    )
    segs = result.get("segments", [])
    return {
        "segments": segs,
        "language": result.get("language", "unknown"),
        "duration_sec": segs[-1]["end"] if segs else 0,
    }


def _transcribe_whisperx(audio_path: str) -> dict:
    import whisperx
    cfg = CONFIG["whisperx"]
    model = whisperx.load_model(
        cfg["model_size"], cfg["device"],
        compute_type=cfg["compute_type"], language=cfg["language"],
    )
    result = model.transcribe(audio_path, batch_size=cfg["batch_size"])
    lang = result.get("language", "unknown")
    try:
        model_a, meta = whisperx.load_align_model(language_code=lang, device=cfg["device"])
        result = whisperx.align(result["segments"], model_a, meta, audio_path, cfg["device"])
    except Exception as e:
        logger.warning(f"alignment 失敗: {e}")
    segs = result.get("segments", [])
    return {
        "segments": segs,
        "language": lang,
        "duration_sec": segs[-1]["end"] if segs else 0,
    }


def _transcribe_openai_cli(audio_path: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = ["whisper", audio_path, "--model", "medium",
               "--output_format", "json", "--output_dir", tmpdir, "--language", "zh"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        json_files = list(Path(tmpdir).glob("*.json"))
        if not json_files:
            raise FileNotFoundError("whisper CLI 無輸出")
        with open(json_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
    segs = data.get("segments", [])
    return {
        "segments": segs,
        "language": data.get("language", "zh"),
        "duration_sec": segs[-1]["end"] if segs else 0,
    }




# ============================================================
# 音訊資訊
# ============================================================

def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    try:
        return float(out)
    except Exception:
        return 0.0


def get_speaker_preview(speakers: dict, top_n: int = 6) -> str:
    """Build a short preview string for speaker mapping UI."""
    if not speakers:
        return "(no speakers)"
    total = sum(v.get("duration_sec", 0) for v in speakers.values()) or 0.0
    items = sorted(speakers.items(), key=lambda kv: kv[1].get("duration_sec", 0), reverse=True)
    lines = []
    for spk, info in items[:top_n]:
        dur = info.get("duration_sec", 0)
        pct = (dur / total * 100) if total else 0
        lines.append(f"  {spk}: {dur/60:.1f}min ({pct:.0f}%)")
    if len(items) > top_n:
        lines.append(f"  ... +{len(items)-top_n} more")
    return "\n".join(lines)


def _clean_quote_text(t: str) -> str:
    t = (t or "").strip()
    # collapse whitespace
    t = re.sub(r"\s+", " ", t)
    # trim common leading speaker marks
    t = re.sub(r"^(?:[-–—•]|\d+[:：])\s*", "", t)
    return t.strip()


_SMALLTALK_PAT = re.compile(
    r"(哈哈|呵呵|嘿嘿|嗯+|呃+|喔+|哦+|欸+|啊+|對+|好+|ok|okay|謝謝|沒事|先這樣|晚點|掰|拜拜|早安|午安|晚安)",
    re.IGNORECASE,
)


def _is_low_signal_segment_text(t: str) -> bool:
    """Heuristic: segment is too short / too filler / too little content."""
    t = _clean_quote_text(t)
    if not t:
        return True
    # too short
    if len(t) < 12:
        return True
    # mostly smalltalk/filler
    if len(t) < 30 and _SMALLTALK_PAT.search(t):
        return True
    # very low CJK/alpha ratio
    content_chars = sum(1 for ch in t if ("\u4e00" <= ch <= "\u9fff") or ch.isalpha() or ch.isdigit())
    if content_chars / max(1, len(t)) < 0.35:
        return True
    return False


def build_speaker_quotes(
    segments: list,
    speakers: dict,
    top_n: int = 3,
    gap_merge_sec: float = 0.8,
) -> dict:
    """Return per-speaker representative quotes.

    Output: {
      spk: {
        "quotes": [{"start": float, "end": float, "text": str}, ...],
        "stats": {...}
      }
    }
    """
    by_spk = {}
    for seg in segments or []:
        spk = seg.get("speaker") or "UNKNOWN"
        text = seg.get("text") or ""
        by_spk.setdefault(spk, []).append({
            "start": float(seg.get("start", 0) or 0),
            "end": float(seg.get("end", 0) or 0),
            "text": text,
        })

    # merge adjacent segments for each speaker to avoid too-fragmented quotes
    merged = {}
    for spk, items in by_spk.items():
        items = sorted(items, key=lambda x: x["start"])
        buf = []
        cur = None
        for it in items:
            t = _clean_quote_text(it["text"])
            if cur is None:
                cur = {"start": it["start"], "end": it["end"], "text": t}
                continue
            if it["start"] - cur["end"] <= gap_merge_sec:
                # merge
                cur["end"] = max(cur["end"], it["end"])
                if t:
                    cur["text"] = (cur["text"] + " " + t).strip() if cur["text"] else t
            else:
                buf.append(cur)
                cur = {"start": it["start"], "end": it["end"], "text": t}
        if cur is not None:
            buf.append(cur)
        merged[spk] = buf

    out = {}
    for spk, items in merged.items():
        # compute stats
        total_chars = sum(len(_clean_quote_text(x.get("text", ""))) for x in items)
        good_items = [x for x in items if not _is_low_signal_segment_text(x.get("text", ""))]
        good_chars = sum(len(_clean_quote_text(x.get("text", ""))) for x in good_items)

        # pick top quotes by length (good first, then fallback)
        pool = good_items if good_items else items
        pool = sorted(pool, key=lambda x: len(_clean_quote_text(x.get("text", ""))), reverse=True)
        quotes = []
        for x in pool:
            txt = _clean_quote_text(x.get("text", ""))
            if not txt:
                continue
            quotes.append({"start": x["start"], "end": x["end"], "text": txt})
            if len(quotes) >= top_n:
                break

        info = (speakers or {}).get(spk, {})
        out[spk] = {
            "quotes": quotes,
            "stats": {
                "duration_sec": float(info.get("duration_sec", 0) or 0),
                "segment_count": int(info.get("segment_count", 0) or 0),
                "total_chars": int(total_chars),
                "good_chars": int(good_chars),
            },
        }

    return out


def filter_non_topic_speakers(
    speakers: dict,
    quotes_by_speaker: dict,
    min_pct: float = 0.06,
    min_duration_sec: float = 60.0,
    min_total_chars: int = 120,
    min_good_chars: int = 80,
) -> tuple[list, list]:
    """Heuristic filter for speakers who are likely off-topic / low-signal.

    Returns: (kept_speakers, ignored_speakers)
    """
    if not speakers:
        return [], []

    total_dur = sum(float(v.get("duration_sec", 0) or 0) for v in speakers.values()) or 0.0
    items = sorted(speakers.keys(), key=lambda s: speakers[s].get("duration_sec", 0), reverse=True)

    kept, ignored = [], []
    for spk in items:
        dur = float(speakers[spk].get("duration_sec", 0) or 0)
        pct = (dur / total_dur) if total_dur else 0.0
        q = (quotes_by_speaker or {}).get(spk, {})
        st = q.get("stats", {})
        total_chars = int(st.get("total_chars", 0) or 0)
        good_chars = int(st.get("good_chars", 0) or 0)

        # Main speaker should almost never be dropped
        if speakers[spk].get("is_main_speaker"):
            kept.append(spk)
            continue

        # low talk volume
        low_volume = (dur < min_duration_sec) or (pct < min_pct)

        # fragmented / unclear content
        low_content = (total_chars < min_total_chars) or (good_chars < min_good_chars)

        if low_volume and low_content:
            ignored.append(spk)
        else:
            kept.append(spk)

    return kept, ignored


def _to_wav_for_pyannote(audio_path: str) -> str:
    """Convert input audio to a temporary mono 16k WAV for pyannote/torchaudio."""
    out = Path(tempfile.mktemp(suffix='.wav', prefix='pyannote_'))
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-i', audio_path,
        '-ac', '1', '-ar', '16000',
        str(out), '-y'
    ]
    subprocess.run(cmd, check=True)
    return str(out)

# ============================================================
# Diarization (獨立)
# ============================================================

def run_diarization(
    audio_path: str,
    segments: list,
    progress_cb: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
) -> tuple:
    """Return: (updated_segments, speakers_summary).

    `progress_cb` is preferred; `progress_callback` kept for backward compat.
    """
    if progress_cb is None:
        progress_cb = progress_callback
    """回傳: (updated_segments, speakers_summary)"""
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        logger.warning("HF_TOKEN 未設定，跳過 diarization")
        return segments, {}

    # Periodic progress heartbeat (avoid Telegram silence/timeouts)
    diarization_heartbeat_stop = None
    if progress_cb:
        import threading
        _hb_stop = threading.Event()
        def _hb():
            t0 = time.time()
            # first ping after 120s, then every 180s
            if not _hb_stop.wait(120):
                while not _hb_stop.is_set():
                    elapsed_min = int((time.time() - t0) / 60)
                    try:
                        progress_cb(f"🎤 Diarization 進行中…（{elapsed_min} 分）")
                    except Exception:
                        pass
                    _hb_stop.wait(180)
        threading.Thread(target=_hb, daemon=True).start()
        diarization_heartbeat_stop = _hb_stop

    try:
        if progress_cb:
            progress_cb("🎤 執行說話者辨識...")

        from pyannote.audio import Pipeline as PyannotePipeline
        t0 = time.time()
        pipe = PyannotePipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=hf_token,
        )
        wav_path = _to_wav_for_pyannote(audio_path)
        dia = pipe(wav_path)
        elapsed = time.time() - t0
        try:
            os.unlink(wav_path)
        except Exception:
            pass

        # Merge diarization → segments
        timeline = [(t.start, t.end, s) for t, _, s in dia.itertracks(yield_label=True)]
        for seg in segments:
            mid = (seg.get("start", 0) + seg.get("end", 0)) / 2
            seg["speaker"] = next(
                (s for a, b, s in timeline if a <= mid <= b), "UNKNOWN"
            )

        # Speaker stats
        stats = {}
        for seg in segments:
            spk = seg.get("speaker", "UNKNOWN")
            dur = seg.get("end", 0) - seg.get("start", 0)
            if spk not in stats:
                stats[spk] = {"duration_sec": 0, "segment_count": 0}
            stats[spk]["duration_sec"] += dur
            stats[spk]["segment_count"] += 1

        if stats:
            main = max(stats, key=lambda s: stats[s]["duration_sec"])
            for spk in stats:
                stats[spk]["is_main_speaker"] = (spk == main)
                stats[spk]["role"] = "主講者(推測)" if spk == main else "其他"

        if progress_cb:
            progress_cb(f"✅ 說話者辨識完成 ({elapsed:.0f}s, {len(stats)} 人)")

        if diarization_heartbeat_stop is not None:
            diarization_heartbeat_stop.set()
        return segments, stats

    except Exception as e:
        logger.warning(f"Diarization 失敗: {e}")
        if progress_cb:
            progress_cb(f"⚠️ 說話者辨識失敗: {e}")
        if diarization_heartbeat_stop is not None:
            diarization_heartbeat_stop.set()
        return segments, {}


# ============================================================
# 音訊切割 / 合併
# ============================================================

def split_audio(audio_path: str, chunk_minutes: int = 30) -> list:
    """將長音訊切割為多個 chunk，回傳檔案路徑清單"""
    output_dir = Path(tempfile.mkdtemp(prefix="whisper_chunks_"))
    pattern = str(output_dir / "chunk_%03d.wav")

    cmd = [
        "ffmpeg", "-i", audio_path,
        "-f", "segment",
        "-segment_time", str(chunk_minutes * 60),
        "-c", "pcm_s16le",   # WAV for compatibility
        "-ar", "16000",       # 16kHz for Whisper
        "-ac", "1",           # mono
        pattern,
        "-y",
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    chunks = sorted(output_dir.glob("chunk_*.wav"))
    logger.info(f"切割完成: {len(chunks)} 個 chunks")
    return [str(c) for c in chunks]


def merge_audio_files(file_paths: list) -> str:
    """合併多個音訊檔，回傳合併後的檔案路徑"""
    output = Path(tempfile.mktemp(suffix=".wav", prefix="merged_"))

    # 建立 ffmpeg concat 清單
    list_file = Path(tempfile.mktemp(suffix=".txt"))
    with open(list_file, "w") as f:
        for p in file_paths:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output), "-y",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    list_file.unlink(missing_ok=True)

    logger.info(f"合併完成: {output}")
    return str(output)
