#!/usr/bin/env python3
"""Load chunks and write transcript + metadata to temp files for LLM processing."""
import json
from pathlib import Path

CHUNK_HASH = "4daace6fb8f9"
CACHE_DIR = Path.home() / "whisperx-outputs" / "cache"
OUT_DIR = Path.home() / "whisperx-outputs" / "tmp"
OUT_DIR.mkdir(exist_ok=True)
CHUNK_MINUTES = 30

def _fmt_ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# Load chunks
chunks = sorted(CACHE_DIR.glob(f"chunk_{CHUNK_HASH}_*.json"),
                key=lambda p: int(p.stem.rsplit("_", 1)[-1]))
all_segments = []
total_dur = 0.0

for i, cp in enumerate(chunks):
    data = json.loads(cp.read_text(encoding="utf-8"))
    offset = i * CHUNK_MINUTES * 60
    for seg in data["segments"]:
        s = dict(seg)
        s["start"] = s.get("start", 0) + offset
        s["end"] = s.get("end", 0) + offset
        all_segments.append(s)
    total_dur = max(total_dur, offset + data.get("duration_sec", 0))

# Build plain transcript
lines = []
for seg in all_segments:
    text = seg.get("text", "").strip()
    if not text:
        continue
    ts = _fmt_ts(seg.get("start", 0))
    lines.append(f"[{ts}] {text}")

transcript = "\n".join(lines)
transcript_path = OUT_DIR / f"transcript_{CHUNK_HASH}.txt"
metadata_path = OUT_DIR / f"metadata_{CHUNK_HASH}.json"

transcript_path.write_text(transcript, encoding="utf-8")
metadata = {
    "chunk_hash": CHUNK_HASH,
    "total_segments": len(all_segments),
    "total_duration_sec": total_dur,
    "duration_text": f"{int(total_dur//3600)}h {int((total_dur%3600)//60):02d}m {int(total_dur%60):02d}s",
    "chunk_count": 9,
    "transcript_chars": len(transcript),
    "course_name": "全球台商個案研討",
    "professor": "林震岩",
    "date": "2026-04-11",
}
metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Transcript: {len(transcript)} chars -> {transcript_path}")
print(f"Metadata: {metadata_path}")
print(f"Duration: {total_dur:.0f}s ({len(all_segments)} segments, 9 chunks)")
