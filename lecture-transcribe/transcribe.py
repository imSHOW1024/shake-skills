from __future__ import annotations

"""
transcribe.py — 轉錄引擎 + Diarization + 音訊處理

三層 fallback: mlx-whisper → WhisperX → openai-whisper CLI
Diarization: pyannote standalone (獨立於轉錄引擎)
音訊處理: ffmpeg 切割 / 合併
"""

# ── PyTorch 2.6+ weights_only fix（必須在所有 torch/whisperx import 之前）──
# PyTorch 2.6 把 torch.load weights_only 預設改為 True，導致 pyannote 模型載入失敗。
# pyannote 模型來自 Hugging Face，屬可信來源。使用 torch 官方環境變數解法。
# skill.yaml env_defaults 應自動設定此值；這裡做一層保底。
import os as _os_for_torch_patch
if not _os_for_torch_patch.environ.get('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'):
    _os_for_torch_patch.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'

import gc
import hashlib
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
        "device": "mps",
        "compute_type": "float16",
        "batch_size": 8,
        "language": None,
    },
    "diarization": {"min_speakers": 1, "max_speakers": 5},
}


# ============================================================
# 轉錄 (三層 Fallback)
# ============================================================

def _preprocess_audio(audio_path: str) -> str:
    """Preprocess audio with ffmpeg (16kHz mono WAV + loudnorm)."""
    out = Path(tempfile.mktemp(suffix='.wav', prefix='prep_'))
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-i', audio_path,
        '-af', 'loudnorm',
        '-ac', '1', '-ar', '16000',
        str(out), '-y'
    ]
    try:
        subprocess.run(cmd, check=True)
        return str(out)
    except Exception as e:
        logger.warning(f"預處理失敗，使用原始檔案: {e}")
        return audio_path

def _detect_silence(audio_path: str, threshold_db: float = -40, min_silence_pct: float = 0.8) -> bool:
    """Return True if audio is mostly silent (> min_silence_pct of duration).

    Uses ffmpeg silencedetect filter to measure silence duration.
    """
    try:
        # Get total duration first
        dur_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        dur_out = subprocess.check_output(dur_cmd, text=True, stderr=subprocess.DEVNULL).strip()
        total_dur = float(dur_out) if dur_out else 0.0
        if total_dur <= 0:
            return False

        # Run silencedetect
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "info",
            "-i", audio_path,
            "-af", f"silencedetect=noise={threshold_db}dB:d=0.5",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stderr or ""

        # Parse silence_duration lines
        silence_durations = re.findall(r"silence_duration:\s*([\d.]+)", output)
        total_silence = sum(float(d) for d in silence_durations)

        silence_pct = total_silence / total_dur
        logger.debug(f"靜音檢測: {audio_path} — 靜音 {total_silence:.1f}s / {total_dur:.1f}s ({silence_pct:.0%})")
        return silence_pct >= min_silence_pct

    except Exception as e:
        logger.warning(f"靜音檢測失敗: {e}")
        return False


def transcribe_audio(
    audio_path: str,
    progress_cb: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    chunk_minutes: int = 30,
) -> dict:
    """Transcribe audio with engine fallback.

    `progress_cb` is the preferred arg name (used by lecture_pipeline.py).
    `progress_callback` is kept for backward compatibility.
    `chunk_minutes`: for audio > 45 minutes, split into chunks of this size.
    """
    if progress_cb is None:
        progress_cb = progress_callback

    dur_sec = get_audio_duration(audio_path)
    long_audio = dur_sec > 45 * 60

    # ── Long audio: chunked transcription with per-chunk caching ──
    if long_audio:
        return _transcribe_chunked(audio_path, dur_sec, chunk_minutes, progress_cb)

    # ── Short audio: existing behaviour ──
    if progress_cb:
        progress_cb("⚙️ 預處理音檔...")
    prep_path = _preprocess_audio(audio_path)

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
            result = fn(prep_path)
            
            # fallback 條件補強: 攔截空字串、空 segments、None 結果
            if not result or not result.get("segments") or not any(s.get("text", "").strip() for s in result.get("segments")):
                raise ValueError("轉錄結果為空 (無 segments 或字串)")
                
            elapsed = time.time() - t0
            result["engine_used"] = name
            result["transcribe_time_sec"] = elapsed
            logger.info(f"{name} OK ({elapsed:.1f}s)")
            if progress_cb:
                progress_cb(f"✅ {name} 完成 ({elapsed:.0f}s)")
            
            if prep_path != audio_path:
                try: os.unlink(prep_path)
                except Exception: pass
                
            return result
        except Exception as e:
            last_error = e
            logger.warning(f"{name} 失敗: {e}")
            if progress_cb:
                progress_cb(f"⚠️ {name} 失敗，嘗試下一個...")

    if prep_path != audio_path:
        try: os.unlink(prep_path)
        except Exception: pass

    raise RuntimeError(f"所有引擎失敗: {last_error}")


def _transcribe_chunked(
    audio_path: str,
    dur_sec: float,
    chunk_minutes: int,
    progress_cb: Optional[Callable],
) -> dict:
    """Split long audio into chunks, transcribe each with per-chunk caching, then merge."""
    if progress_cb:
        progress_cb(f"⏳ 長音訊模式：切割為 {chunk_minutes} 分鐘段落...")

    # Per-chunk cache dir
    cache_dir = Path.home() / "whisperx-outputs" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Stable hash of the source file for cache keys
    file_hash = hashlib.md5(f"{Path(audio_path).stem}__{Path(audio_path).stat().st_size}".encode()).hexdigest()[:12]

    chunks = split_audio(audio_path, chunk_minutes=chunk_minutes)
    total = len(chunks)
    if progress_cb:
        progress_cb(f"🔪 切割完成：{total} 段")

    all_segments = []
    engine_used = None

    # For WhisperX (fallback only), load once before the loop.
    # mlx-whisper is priority 1 on Apple Silicon; only load WhisperX if mlx-whisper is unavailable.
    _whisperx_model = None
    try:
        import mlx_whisper as _mlx_check  # noqa: F401
        logger.info("mlx-whisper available — skipping WhisperX preload")
    except ImportError:
        try:
            import whisperx as _wx
            cfg = CONFIG["whisperx"]
            _whisperx_model = _wx.load_model(
                cfg["model_size"], cfg["device"],
                compute_type=cfg["compute_type"], language=cfg["language"],
            )
            logger.info("WhisperX 模型預載完成（mlx-whisper 不可用時的 fallback）")
        except Exception as e:
            logger.warning(f"WhisperX 模型預載失敗（將 per-chunk fallback）: {e}")

    try:
        for i, chunk_path in enumerate(chunks):
            chunk_cache_path = cache_dir / f"chunk_{file_hash}_{i}.json"

            # ── Per-chunk cache hit ──
            if chunk_cache_path.exists():
                try:
                    cached = json.loads(chunk_cache_path.read_text(encoding="utf-8"))
                    if isinstance(cached, dict) and cached.get("segments"):
                        logger.info(f"Chunk {i} 快取命中")
                        _merge_chunk_segments(all_segments, cached["segments"], i, chunk_minutes)
                        if not engine_used:
                            engine_used = cached.get("engine_used", "cached")
                        if progress_cb:
                            progress_cb(f"♻️ 轉錄進度：{i+1}/{total} 段（快取）")
                        continue
                except Exception:
                    pass  # corrupt cache → re-transcribe

            # ── Silence detection ──
            if _detect_silence(chunk_path):
                logger.info(f"Chunk {i} 跳過靜音段")
                if progress_cb:
                    progress_cb(f"🔇 轉錄進度：{i+1}/{total} 段 — 跳過靜音段")
                # Save empty result to cache so we don't re-check next time
                chunk_cache_path.write_text(
                    json.dumps({"segments": [], "engine_used": "silence_skip", "duration_sec": 0}, ensure_ascii=False),
                    encoding="utf-8"
                )
                continue

            # ── Preprocess chunk ──
            prep_chunk = _preprocess_audio(chunk_path)

            # ── Transcribe chunk ──
            chunk_result = None
            last_err = None

            # Priority 1: mlx-whisper (Apple Silicon GPU — fastest on M1/M2/M3)
            try:
                chunk_result = _transcribe_mlx(prep_chunk)
                chunk_result["engine_used"] = "mlx-whisper"
                if not chunk_result.get("segments") or not any(s.get("text", "").strip() for s in chunk_result["segments"]):
                    chunk_result = None
                    raise ValueError("mlx-whisper chunk 結果為空")
            except Exception as e:
                last_err = e
                logger.warning(f"Chunk {i} mlx-whisper 失敗: {e}")
                chunk_result = None

            # Priority 2: WhisperX (fallback, model already loaded if available)
            if chunk_result is None and _whisperx_model is not None:
                try:
                    import whisperx as _wx
                    cfg = CONFIG["whisperx"]
                    raw = _whisperx_model.transcribe(prep_chunk, batch_size=cfg["batch_size"])
                    lang = raw.get("language", "unknown")
                    try:
                        model_a, meta = _wx.load_align_model(language_code=lang, device=cfg["device"])
                        raw = _wx.align(raw["segments"], model_a, meta, prep_chunk, cfg["device"])
                        del model_a, meta
                        gc.collect()
                    except Exception as ae:
                        logger.warning(f"Chunk {i} alignment 失敗: {ae}")
                    segs = raw.get("segments", [])
                    chunk_result = {"segments": segs, "language": lang,
                                    "duration_sec": segs[-1]["end"] if segs else 0,
                                    "engine_used": "whisperx"}
                    if not segs or not any(s.get("text", "").strip() for s in segs):
                        chunk_result = None
                        raise ValueError("WhisperX chunk 結果為空")
                except Exception as e:
                    last_err = e
                    logger.warning(f"Chunk {i} WhisperX 失敗: {e}")
                    chunk_result = None

            # Priority 3: openai-whisper CLI (last resort)
            if chunk_result is None:
                try:
                    chunk_result = _transcribe_openai_cli(prep_chunk)
                    chunk_result["engine_used"] = "openai-whisper"
                except Exception as e:
                    last_err = e
                    logger.warning(f"Chunk {i} openai-whisper 失敗: {e}")
                    chunk_result = None

            # Clean up temp preprocessed file
            if prep_chunk != chunk_path:
                try:
                    os.unlink(prep_chunk)
                except Exception:
                    pass

            if chunk_result is None:
                logger.error(f"Chunk {i} 所有引擎失敗，跳過: {last_err}")
                if progress_cb:
                    progress_cb(f"⚠️ 轉錄進度：{i+1}/{total} 段 — 失敗跳過")
                continue

            # ── Cache chunk result ──
            try:
                chunk_cache_path.write_text(
                    json.dumps(chunk_result, ensure_ascii=False),
                    encoding="utf-8"
                )
            except Exception:
                pass

            # ── Merge with time offset ──
            if not engine_used:
                engine_used = chunk_result.get("engine_used", "whisperx")
            _merge_chunk_segments(all_segments, chunk_result.get("segments", []), i, chunk_minutes)

            # Memory management
            del chunk_result
            gc.collect()

            if progress_cb:
                progress_cb(f"🎙️ 轉錄進度：{i+1}/{total} 段完成")

    finally:
        # Delete WhisperX model after all chunks
        if _whisperx_model is not None:
            try:
                del _whisperx_model
                gc.collect()
            except Exception:
                pass

        # Clean up chunk temp files
        for chunk_path in chunks:
            try:
                os.unlink(chunk_path)
            except Exception:
                pass
        # Clean up chunk temp dir
        try:
            chunk_dir = Path(chunks[0]).parent if chunks else None
            if chunk_dir and chunk_dir.exists():
                chunk_dir.rmdir()
        except Exception:
            pass

    if not all_segments:
        raise RuntimeError("所有 chunk 轉錄失敗，無有效 segments")

    total_dur = all_segments[-1]["end"] if all_segments else dur_sec
    return {
        "segments": all_segments,
        "language": "mixed",
        "duration_sec": total_dur,
        "engine_used": engine_used or "whisperx",
        "transcribe_time_sec": 0,  # not tracked per-chunk
    }


def _merge_chunk_segments(all_segments: list, chunk_segs: list, chunk_index: int, chunk_minutes: int) -> None:
    """Append chunk segments to all_segments with correct time offset."""
    offset = chunk_index * chunk_minutes * 60
    for seg in chunk_segs:
        new_seg = dict(seg)
        new_seg["start"] = float(seg.get("start", 0)) + offset
        new_seg["end"] = float(seg.get("end", 0)) + offset
        all_segments.append(new_seg)


def _transcribe_mlx(audio_path: str) -> dict:
    import mlx_whisper
    model = CONFIG["mlx_whisper"]["model"]
    # Do NOT pass language= so mlx-whisper auto-detects per-segment (supports CN/JP mixed)
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
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use large-v3 for better multilingual (CN/JP) performance
        # No --language flag: let Whisper auto-detect
        cmd = ["whisper", audio_path, "--model", "large-v3", "--device", device,
               "--output_format", "json", "--output_dir", tmpdir]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        json_files = list(Path(tmpdir).glob("*.json"))
        if not json_files:
            raise FileNotFoundError("whisper CLI 無輸出")
        with open(json_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
    segs = data.get("segments", [])
    return {
        "segments": segs,
        "language": data.get("language", "unknown"),
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

        import torch
        from pyannote.audio import Pipeline as PyannotePipeline

        # 選擇最佳 device：MPS (Apple Silicon) > CUDA > CPU
        if torch.backends.mps.is_available():
            _dia_device = torch.device("mps")
            logger.info("Diarization device: MPS (Apple Silicon GPU)")
        elif torch.cuda.is_available():
            _dia_device = torch.device("cuda")
            logger.info("Diarization device: CUDA GPU")
        else:
            _dia_device = torch.device("cpu")
            logger.info("Diarization device: CPU")

        t0 = time.time()
        pipe = PyannotePipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=hf_token,
        )
        try:
            pipe = pipe.to(_dia_device)
        except Exception as _mps_err:
            logger.warning(f"Diarization: 無法使用 {_dia_device}，回退 CPU ({_mps_err})")
            _dia_device = torch.device("cpu")
            pipe = pipe.to(_dia_device)

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
