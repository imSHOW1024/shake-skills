"""
lecture_pipeline.py v3 — 錄音 → 摘要 → Notion 完整 Pipeline

功能:
  - 雙 DB 路由 (EMBA 課堂 / 商務會談)
  - 四種摘要模板自動切換
  - Speaker 兩階段識別 (預填 + 校正)
  - 多段錄音合併
  - 長音訊自動切割
  - 逐字稿 toggle heading 收合
  - LLM 模型可指定

入口: handle_audio_message() — 由 OpenClaw Telegram handler 呼叫
"""

import os
import time
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from transcribe import (
    transcribe_audio, run_diarization, get_audio_duration,
    merge_audio_files, get_speaker_preview,
    build_speaker_quotes, filter_non_topic_speakers,
)
from summary_prompts import (
    select_template, select_model, select_chunk_model,
    build_summary_prompt, build_system_prompt, build_chunk_prompt, build_reduce_prompt,
    TEMPLATE_NAMES,
)
from notion_upload import upload_emba, upload_business

logger = logging.getLogger(__name__)

CONFIG = {
    "schedule_path": Path(__file__).parent / "course_schedule.yaml",
    "output_dir": Path.home() / "whisperx-outputs",
    # Cache transcripts so a gateway restart or retry doesn't re-transcribe long audio.
    # (Safe: stored locally under the output dir only.)
    "cache_dir": Path.home() / "whisperx-outputs" / "cache",
}



# ============================================================
# DOCX export (summary only)
# ============================================================

def _write_summary_docx(summary_md: str, metadata: dict, out_dir: Path):
    '''Write summary markdown as a simple DOCX.'''
    try:
        from docx import Document
        from docx.shared import Pt
    except Exception:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    name = (metadata.get('course_name') or metadata.get('meeting_name') or 'rec')
    name = name.replace('/', '-').replace(' ', '_')
    date = metadata.get('date', 'x')
    docx_path = out_dir / f"{date}_{name}.docx"

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(11)

    title = metadata.get('meeting_name') or metadata.get('course_name') or '摘要'
    doc.add_heading(f"{date} {title}", level=1)

    if metadata.get('company'):
        doc.add_paragraph(f"對象公司：{metadata.get('company')}")
    if metadata.get('location'):
        doc.add_paragraph(f"地點：{metadata.get('location')}")
    if metadata.get('attendees'):
        doc.add_paragraph(f"與會：{', '.join(metadata.get('attendees') or [])}")

    doc.add_paragraph('')

    for ln in (summary_md or '').split("\n"):
        s = ln.rstrip()
        if not s:
            doc.add_paragraph('')
            continue
        if s.startswith('### '):
            doc.add_heading(s[4:], level=3)
        elif s.startswith('## '):
            doc.add_heading(s[3:], level=2)
        elif s.startswith('# '):
            doc.add_heading(s[2:], level=1)
        else:
            doc.add_paragraph(s)

    doc.save(docx_path)
    return docx_path

async def _send_docx_to_chat(send_message, docx_path: Path, caption: str = ""):
    """Best-effort Telegram document sending.

    OpenClaw skill runtimes may provide different send_message signatures.
    We try a few common patterns and fall back to sending the path.
    """
    if not docx_path:
        return
    try:
        # Pattern 1: send_message(text, file_path=...)
        await send_message(caption or "📎 摘要 DOCX", file_path=str(docx_path))
        return
    except Exception:
        pass

    try:
        # Pattern 2: send_message(dict)
        await send_message({"type": "document", "path": str(docx_path), "caption": caption or "📎 摘要 DOCX"})
        return
    except Exception:
        pass

    try:
        # Fallback: just send a hint
        await send_message(f"📎 DOCX 已產出：{docx_path}")
    except Exception:
        pass




# ============================================================
# 連結音訊下載（Google Drive / OneDrive 公開分享）
# ============================================================

_URL_RE = re.compile(r"https?://[^\s<>]+", re.I)


def _want_diarization(text: str) -> bool:
    """Heuristic: only run diarization when the user explicitly asks for speaker separation.

    Default is OFF for stability/speed on long recordings.
    """
    t = (text or '').lower()
    keys = [
        'speaker', 'speakers', 'diarization',
        '分辨speaker', '分辨 speaker', '辨識speaker', '辨識 speaker',
        '說話者', '講者', '誰講', '誰在講',
    ]
    return any(k in t for k in keys)


def _pick_first_url(text: str) -> str:
    if not (text or '').strip():
        return ''
    m = _URL_RE.search(text)
    return m.group(0).rstrip(').,]') if m else ''


def _extract_drive_file_id(url: str) -> str:
    """Extract Google Drive file id from common share links."""
    if not url:
        return ''
    # /file/d/<id>/
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # ?id=<id>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return ''


def _normalize_download_url(url: str) -> tuple[str, str]:
    """Return (download_url, source_kind)."""
    u = (url or '').strip()
    if not u:
        return '', ''

    low = u.lower()

    # Google Drive
    if 'drive.google.com' in low or 'docs.google.com' in low:
        fid = _extract_drive_file_id(u)
        if fid:
            return f"https://drive.google.com/uc?export=download&id={fid}", 'gdrive'
        return u, 'gdrive'

    # OneDrive
    if '1drv.ms' in low or 'onedrive.live.com' in low:
        # Most share links accept download=1
        if 'download=1' not in low:
            sep = '&' if '?' in u else '?'
            u = f"{u}{sep}download=1"
        return u, 'onedrive'

    return u, 'generic'


def _http_download(url: str, out_path: Path, kind: str = 'generic') -> Path:
    """Download URL to out_path. Handles Google Drive confirm token for large files."""
    import urllib.request
    import urllib.parse

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # cookie jar helps with Google Drive confirm token
    cj = None
    opener = None
    try:
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    except Exception:
        opener = urllib.request.build_opener()

    def fetch(u: str):
        req = urllib.request.Request(u, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
        })
        return opener.open(req, timeout=60)

    # First request
    resp = fetch(url)

    # Google Drive sometimes returns an HTML page with a confirm token
    if kind == 'gdrive':
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if 'text/html' in ctype:
            body = resp.read(200000).decode('utf-8', errors='ignore')
            mm = re.search(r"confirm=([0-9A-Za-z_]+)", body)
            if not mm:
                # older pattern
                mm = re.search(r"name=\"confirm\"\s+value=\"([0-9A-Za-z_]+)\"", body)
            if mm:
                token = mm.group(1)
                parsed = urllib.parse.urlparse(url)
                q = dict(urllib.parse.parse_qsl(parsed.query))
                q['confirm'] = token
                new_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q)))
                resp = fetch(new_url)

    # Try infer filename
    cd = resp.headers.get('Content-Disposition') or ''
    fname = ''
    m = re.search(r'filename\*=UTF-8\'\'([^;]+)', cd)
    if m:
        fname = urllib.parse.unquote(m.group(1))
    else:
        m = re.search(r'filename="?([^";]+)"?', cd)
        if m:
            fname = m.group(1)

    final_path = out_path
    if fname:
        safe = fname.replace('/', '-')
        final_path = out_path.with_name(safe)

    with open(final_path, 'wb') as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    return final_path


def _download_shared_audio(url: str, out_dir: Path) -> Path:
    dl, kind = _normalize_download_url(url)
    if not dl:
        raise ValueError('empty url')

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = out_dir / f"link_{ts}.bin"
    p = _http_download(dl, out, kind=kind)
    return p

# ============================================================
# 課表推斷
# ============================================================

def _load_schedule():
    p = CONFIG["schedule_path"]
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("courses", [])


def _infer_course(dt=None):
    if dt is None:
        dt = datetime.now()
    courses = _load_schedule()
    iso_wd = dt.weekday() + 1
    cur_time = dt.strftime("%H:%M")

    for c in courses:
        if c["day"] == iso_wd and c["start"] <= cur_time <= c["end"]:
            return {
                "course_name": c["name"], "professor": c["professor"],
                "room": c.get("room", ""), "date": dt.strftime("%Y-%m-%d"),
                "day_of_week": "一二三四五六日"[dt.weekday()],
                "auto_detected": True, "type": "emba",
            }
    return {
        "course_name": "", "professor": "", "room": "",
        "date": dt.strftime("%Y-%m-%d"),
        "day_of_week": "一二三四五六日"[dt.weekday()],
        "auto_detected": False, "type": "",
    }



# ============================================================
# 互動式補齊使用者提供的會議/課堂資訊
# ============================================================

_DEF_TOPIC_KEYS = ["摘要主題", "主題", "課程", "會議"]


def _extract_user_fields(text: str) -> dict:
    """Best-effort parse for user-provided context in caption/message text."""
    if not (text or '').strip():
        return {}
    t = text.strip()
    out = {}
    # Patterns like: 主題: xxx
    for key in ["摘要主題", "主題", "日期", "時間", "日期/時間", "地點", "人員", "與會", "參與", "參加", "DB", "資料庫", "模板", "Template", "template"]:
        mm = re.search(rf"{re.escape(key)}\s*[:：]\s*(.+)", t)
        if mm:
            out[key] = mm.group(1).strip()
    return out


def _parse_date_time_answer(ans: str, fallback_date: str) -> tuple[str, str]:
    """Return (date, time). Accepts: YYYY-MM-DD HH:MM | YYYY/MM/DD HH:MM | HH:MM | YYYY-MM-DD."""
    a = (ans or '').strip()
    if not a:
        return fallback_date, ""

    a = a.replace('/', '-')
    # full datetime
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})$", a)
    if m:
        return m.group(1), m.group(2)
    # date only
    m = re.match(r"^(\d{4}-\d{2}-\d{2})$", a)
    if m:
        return m.group(1), ""
    # time only
    m = re.match(r"^(\d{1,2}:\d{2})$", a)
    if m:
        return fallback_date, m.group(1)

    return fallback_date, a


def _suggest_db_type(recording_time, topic: str) -> str:
    """Return suggested type: 'emba' or 'business'."""
    t = (topic or '').lower()
    if any(k in t for k in ["emba", "課堂", "教授", "個案", "作業", "期末"]):
        return 'emba'
    if recording_time is not None:
        inf = _infer_course(recording_time)
        if inf.get('auto_detected'):
            return 'emba'
    return 'business'


async def _ask_common_context(send_message, ask_user, metadata: dict, provided: dict) -> dict:
    """Ask for topic/date-time/location/people when missing."""
    # 1) topic
    topic = provided.get('摘要主題') or provided.get('主題')
    if not (topic or '').strip():
        await send_message("我需要幾個資訊幫尼把摘要整理得更準：\n1) 摘要主題  2) 日期/時間  3) 地點  4) 人員")
        topic = await ask_user("摘要主題")
    topic = (topic or '').strip()

    # 2) date/time
    dt_ans = provided.get('日期/時間') or ''
    if not dt_ans:
        # allow separate date/time
        d = (provided.get('日期') or '').strip()
        tm = (provided.get('時間') or '').strip()
        if d and tm:
            dt_ans = f"{d} {tm}"
        elif d:
            dt_ans = d
        elif tm:
            dt_ans = tm

    if not (dt_ans or '').strip():
        dt_ans = await ask_user(f"日期/時間（可只回時間；預設 {metadata.get('date','')}）")

    date, tm = _parse_date_time_answer(dt_ans, metadata.get('date',''))
    metadata['date'] = date
    if tm:
        metadata['time'] = tm

    # 3) location
    loc = provided.get('地點') or metadata.get('location') or metadata.get('room')
    if not (loc or '').strip():
        loc = await ask_user("地點")
    metadata['location'] = (loc or '').strip()

    # 4) people
    ppl = provided.get('人員') or provided.get('與會') or provided.get('參與') or ''
    if not (ppl or '').strip():
        ppl = await ask_user("人員（逗號分隔；不知道可回 ok）")
    ppl = (ppl or '').strip()
    people_list = []
    if ppl.lower() not in ('ok','跳過',''):
        people_list = [x.strip() for x in ppl.split(',') if x.strip()]

    metadata['attendees'] = people_list
    metadata['participants'] = people_list

    # store topic in both keys (downstream compatibility)
    metadata.setdefault('course_name', '')
    metadata.setdefault('meeting_name', '')
    if not metadata.get('course_name'):
        metadata['course_name'] = topic
    if not metadata.get('meeting_name'):
        metadata['meeting_name'] = topic

    return metadata

# ============================================================
# Markdown 生成
# ============================================================

def _build_transcript_md(segments, speakers):
    """逐字稿 Markdown (toggle heading 用)"""
    main_spk = next((s for s, i in speakers.items() if i.get("is_main_speaker")), None)
    lines = []

    if speakers:
        total = sum(s["duration_sec"] for s in speakers.values())
        lines.extend(["## 說話者統計", "",
                       "| 說話者 | 角色 | 發言時長 | 比例 |",
                       "|--------|------|----------|------|"])
        for spk, info in sorted(speakers.items(), key=lambda x: x[1]["duration_sec"], reverse=True):
            name = info.get("display_name", spk)
            pct = f"{info['duration_sec']/total*100:.0f}%" if total else "?"
            lines.append(f"| {name} | {info.get('role','')} | {_fmt_dur(info['duration_sec'])} | {pct} |")

    lines.extend(["", "## 完整逐字稿", ""])
    cur_spk = None
    for seg in segments:
        spk = seg.get("speaker", "")
        text = seg.get("text", "").strip()
        if not text:
            continue
        if spk and spk != cur_spk:
            cur_spk = spk
            name = speakers.get(spk, {}).get("display_name", spk)
            lines.extend(["", f"**{name}** `[{_fmt_ts(seg.get('start', 0))}]`", ""])
        lines.append(text)
    return "\n".join(lines)


def _build_transcript_plain(segments, speakers):
    """純文字逐字稿 (LLM 摘要用)"""
    lines = []
    for seg in segments:
        spk = seg.get("speaker", "")
        name = speakers.get(spk, {}).get("display_name", spk) if spk else ""
        text = seg.get("text", "").strip()
        ts = _fmt_ts(seg.get("start", 0))
        lines.append(f"[{ts}] {name}: {text}" if name else f"[{ts}] {text}")
    return "\n".join(lines)


def _chunk_segments_for_llm(segments, speakers, max_chars: int = 12000, max_minutes: int = 12):
    """Split transcript into chunk texts for LLM.

    Design goals:
    - keep each chunk small enough for fast/cheap models
    - avoid LLM context explosion for multi-hour audio
    """
    chunks = []
    buf = []
    chunk_start = None
    last_ts = 0

    def flush():
        nonlocal buf, chunk_start, last_ts
        if not buf:
            return
        start_ts = _fmt_ts(chunk_start or 0)
        end_ts = _fmt_ts(last_ts or (chunk_start or 0))
        label = f"{start_ts}-{end_ts}"
        chunks.append({"label": label, "text": "\n".join(buf)})
        buf = []
        chunk_start = None

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        st = int(seg.get("start") or 0)
        last_ts = st
        if chunk_start is None:
            chunk_start = st

        spk = seg.get("speaker", "")
        name = speakers.get(spk, {}).get("display_name", spk) if spk else ""
        ts = _fmt_ts(st)
        line = f"[{ts}] {name}: {text}" if name else f"[{ts}] {text}"

        # flush by time window
        if chunk_start is not None and (st - chunk_start) >= max_minutes * 60 and buf:
            flush()
            chunk_start = st

        # flush by char budget
        if sum(len(x) for x in buf) + len(line) + 1 > max_chars and buf:
            flush()
            chunk_start = st

        buf.append(line)

    flush()
    return chunks



# ============================================================
# 類別正規化
# ============================================================

def _norm_category(t):
    m = {"出差": "出差🟠", "來訪": "來訪🔵", "線上": "線上🟣",
         "online": "線上🟣", "visit": "來訪🔵"}
    return m.get(t.strip().lower(), t.strip())

def _norm_dept(t):
    m = {"ws": "WS業務🟢", "wq": "WQ品管🔴", "跨部門": "跨部門🟡",
         "業務": "WS業務🟢", "品管": "WQ品管🔴"}
    return m.get(t.strip().lower(), t.strip())

def _extract_action_items(md):
    items = []
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("- [ ]") or s.startswith("- [x]"):
            items.append(s[6:].strip())
    return "\n".join(f"{i+1}. {it}" for i, it in enumerate(items)) if items else ""



def _extract_report_lines(summary: str):
    """Extract numbered report lines for business report code block.

    Priority:
    1) Lines under '### 業務會報版摘要' section (if present)
    2) Any numbered list lines '1. ...' in the whole summary (for template R)
    """
    if not summary:
        return []

    lines = summary.split('\n')

    # 1) Prefer section-based extraction
    out = []
    in_sec = False
    for ln in lines:
        s = ln.strip()
        if s.startswith('### ') and '業務會報版摘要' in s:
            in_sec = True
            continue
        if in_sec and s.startswith('### '):
            break
        if in_sec and re.match(r'^\d+\.', s):
            out.append(s)
    if out:
        return out

    # 2) Fallback: grab any numbered list lines
    for ln in lines:
        s = ln.strip()
        if re.match(r'^\d+\.', s):
            out.append(s)
    return out
def _fmt_dur(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"

def _fmt_ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ============================================================
# LLM 呼叫
# ============================================================

async def _call_llm(model_id, system_prompt, user_message, send_message=None, max_tokens: int = 8000, retries: int = 3):
    """
    呼叫 LLM。優先走 OpenClaw routing，fallback 直接 API。
    """
    import asyncio
    # 方式 1: OpenClaw 內建 (根據實際架構調整 import)
    try:
        from openclaw.llm import chat_completion
        last_err = None
        for attempt in range(retries):
            try:
                resp = await chat_completion(
                    model=model_id, system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=max_tokens,
                )
                return resp.get("content", "")
            except Exception as e:
                last_err = e
                # basic backoff for rate-limit / transient errors
                await asyncio.sleep(min(8, 2 ** attempt))
        raise last_err
    except ImportError:
        pass

    # 方式 2: Anthropic API 直接呼叫
    if "claude" in model_id or "anthropic" in model_id:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    # Fallback
    logger.warning(f"模型 {model_id} 無直接 API，fallback Claude")
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return resp.content[0].text


# ============================================================
# 主流程
# ============================================================

async def handle_audio_message(
    audio_path, send_message, ask_user,
    recording_time=None, pending_files=None,
    message_text: Optional[str] = None,
    caption: Optional[str] = None,
    **kwargs,
):
    """
    完整流程入口。由 OpenClaw Telegram handler 呼叫。
    """
    def progress(msg):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_message(msg))
        except RuntimeError:
            logger.info(msg)

    # ===== 多檔合併 =====
    if pending_files and len(pending_files) > 1:
        file_list = "\n".join(
            f"  {i+1}. {Path(f).name} ({get_audio_duration(f)/60:.0f}min)"
            for i, f in enumerate(pending_files)
        )
        await send_message(
            f"🎙️ 偵測到 {len(pending_files)} 個音訊檔:\n{file_list}\n\n"
            f"  1️⃣ 合併為同一場\n  2️⃣ 分開處理"
        )
        r = await ask_user("合併?")
        if r.strip() in ("1", "合併"):
            merged = str(CONFIG["output_dir"] / "merged_audio.m4a")
            CONFIG["output_dir"].mkdir(parents=True, exist_ok=True)
            audio_path = merge_audio_files(pending_files, merged)
            await send_message(f"✅ 合併完成 ({get_audio_duration(audio_path)/60:.0f}min)")
        else:
            audio_path = pending_files[0]
            await send_message("👌 先處理第一段")

    # ===== Step 1: 類型 + Metadata =====
    dur_sec = get_audio_duration(audio_path)
    dur_min = dur_sec / 60

    # Base metadata (date/day-of-week) inferred from recording_time or now
    metadata = _infer_course(recording_time)

    # Parse any user-provided context from caption/message
    ctx_text = (caption or '') + "\n" + (message_text or '')
    provided = _extract_user_fields(ctx_text)

    if metadata["auto_detected"]:
        # EMBA 自動（課表命中）
        # 仍允許補齊地點/人員/時間等資訊
        await send_message(
            f"📚 EMBA 課堂:\n"
            f"  {metadata['course_name']} / {metadata['professor']}\n"
            f"  {metadata['date']} 週{metadata['day_of_week']} / {dur_min:.0f}min\n\n"
            f"我再跟尼確認一下：地點/人員/時間有需要補嗎？（沒有就回 ok）"
        )
        extra = await ask_user("補充")
        if (extra or '').lower() not in ("ok", "跳過", ""):
            if "," in extra:
                metadata["attendees"] = [x.strip() for x in extra.split(",") if x.strip()]
                metadata["participants"] = metadata["attendees"]
            else:
                metadata["location"] = extra.strip()

        await send_message("補充關鍵字? (逗號分隔 或 ok)")
        kw = await ask_user("關鍵字")
        metadata["keywords"] = (
            [k.strip() for k in (kw or '').split(",") if k.strip()]
            if (kw or '').lower() not in ("ok", "跳過", "") else []
        )
        metadata["model_pref"] = None
        metadata["type"] = "emba"

    else:
        # 使用者沒主動給錄音資訊時：主動問『摘要需要的 4 個欄位』
        # 並在需要 DB 路由（課堂 vs 商務）時，先詢問要上傳到哪個 DB。
        await send_message(
            f"📝 收到錄音 ({metadata['date']} 週{metadata['day_of_week']}, {dur_min:.0f}min)"
        )

        # 5) DB 選擇（以錄音上傳時間 + 主題做建議，但仍請使用者確認）
        chosen = None
        t_hint = (provided.get('DB') or provided.get('資料庫') or '').lower()
        if any(k in t_hint for k in ("課堂", "emba", "class")):
            chosen = 'emba'
        elif any(k in t_hint for k in ("商務", "會談", "meeting", "business")):
            chosen = 'business'

        if not chosen:
            # Need topic first for a better suggestion
            if not (provided.get('摘要主題') or provided.get('主題')):
                await send_message("我先問一句：這段錄音的『摘要主題』是？")
                provided['主題'] = (await ask_user("摘要主題")).strip()

            suggest = _suggest_db_type(recording_time, provided.get('摘要主題') or provided.get('主題') or '')
            sug_label = '課堂摘要DB' if suggest == 'emba' else '商務會談DB'
            await send_message(
                "📤 這份摘要要上傳到哪個 Notion DB？\n"
                "  1️⃣ 📚 課堂摘要DB\n"
                "  2️⃣ 💼 商務會談DB\n\n"
                f"我猜是：{sug_label}（但我想跟尼確認）"
            )
            db = await ask_user("上傳DB")
            if db.strip() in ("1", "課堂", "emba"):
                chosen = 'emba'
            elif db.strip() in ("2", "商務", "會談", "business", ""):
                chosen = 'business'
            else:
                chosen = 'other'

        metadata['type'] = chosen

        # 1-4) 補齊摘要所需資訊
        metadata = await _ask_common_context(send_message, ask_user, metadata, provided)

        # 類型專屬補充
        if metadata['type'] == 'emba':
            await send_message("再補兩個欄位就好：課程名稱 / 教授（不確定可回 ok）")
            info = await ask_user("課程/教授")
            parts = [p.strip() for p in (info or '').split("/")]
            if parts and parts[0] and parts[0].lower() not in ('ok','跳過'):
                metadata['course_name'] = parts[0]
                metadata['meeting_name'] = parts[0]
            if len(parts) > 1 and parts[1] and parts[1].lower() not in ('ok','跳過'):
                metadata['professor'] = parts[1]
            # keywords optional
            await send_message("關鍵字(選填，逗號分隔；沒有就回 ok)")
            kw = await ask_user("關鍵字")
            metadata["keywords"] = (
                [k.strip() for k in (kw or '').split(",") if k.strip()]
                if (kw or '').lower() not in ("ok", "跳過", "") else []
            )
            metadata['model_pref'] = None

        elif metadata['type'] == 'business':
            # Template hint (talk/forum)
            topic_hint = (metadata.get('topic') or provided.get('摘要主題') or provided.get('主題') or '').lower()
            if any(k in topic_hint for k in ("演講", "論壇", "講座", "keynote", "speech", "panel")):
                metadata['template_override'] = 'E'

            # Allow user to force template via caption/message: 模板: E
            t_in = (provided.get('模板') or provided.get('Template') or provided.get('template') or '').strip()
            if t_in:
                metadata['template_override'] = t_in.strip().upper()

            await send_message(
                "（選填，但會讓 Notion 欄位更完整）回覆 / 分隔：\n"
                "  對象公司 / 類別(出差/來訪/線上) / 課別(WS/WQ/跨部門) / 模型(選填)\n\n"
                "例: SUBARU-JP / 來訪 / WS\n\n"
                "另外：如果這次是『論壇/演講活動』摘要，尼可以回我：模板 E（不回就自動判斷）"
            )
            biz2 = await ask_user("補充")
            p2 = [x.strip() for x in (biz2 or '').split("/")]
            if len(p2) > 0 and p2[0] and p2[0].lower() not in ('ok','跳過'):
                metadata['company'] = p2[0]
                metadata['target_company'] = p2[0]
            if len(p2) > 1 and p2[1] and p2[1].lower() not in ('ok','跳過'):
                metadata['category'] = _norm_category(p2[1])
            if len(p2) > 2 and p2[2] and p2[2].lower() not in ('ok','跳過'):
                metadata['department'] = _norm_dept(p2[2])
            if len(p2) > 3 and p2[3] and p2[3].lower() not in ('ok','跳過'):
                metadata['model_pref'] = p2[3].strip()

            # Ask template override (optional, default auto)
            if not metadata.get('template_override'):
                await send_message("模板(選填)：A/B/C/E（E=論壇/演講）。不指定就自動判斷，直接回 ok 也行。")
                tv = await ask_user("模板")
                if (tv or '').strip() and (tv or '').strip().lower() not in ('ok','跳過'):
                    metadata['template_override'] = (tv or '').strip().upper()

            metadata['keywords'] = []

        else:
            metadata['course_name'] = metadata.get('course_name') or '其他錄音'
            metadata['model_pref'] = None


    # ===== Step 2: 轉錄（含本地快取，避免重跑） =====
    await send_message("🎙️ 開始轉錄...")

    cache_dir = CONFIG.get("cache_dir") or (CONFIG["output_dir"] / "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    ap = Path(audio_path)
    cache_key = f"{ap.stem}__{int(ap.stat().st_mtime)}__{ap.stat().st_size}.transcribe.json"
    cache_path = cache_dir / cache_key

    tx = None
    if cache_path.exists():
        try:
            import json
            tx = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(tx, dict) and tx.get("segments"):
                await send_message(f"♻️ 使用已轉錄快取：{cache_path.name}")
        except Exception:
            tx = None

    if tx is None:
        t0 = time.time()
        try:
            tx = transcribe_audio(audio_path, progress_cb=progress)
        except Exception as e:
            await send_message(f"❌ 轉錄失敗: {e}")
            return

        # write cache for stability
        try:
            import json
            cache_path.write_text(json.dumps(tx, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        elapsed = time.time() - t0
        engine = tx.get("engine_used", "")
        ratio = tx["duration_sec"] / elapsed if elapsed > 0 else 0
        await send_message(
            f"✅ 轉錄完成 | {engine} | {elapsed:.0f}s ({ratio:.1f}x)\n"
            f"  {_fmt_dur(tx['duration_sec'])} / {len(tx['segments'])} 段"
        )
    else:
        engine = tx.get("engine_used", "(cached)")
        await send_message(
            f"✅ 轉錄完成 | {engine}\n"
            f"  {_fmt_dur(tx.get('duration_sec', 0))} / {len(tx.get('segments', []) or [])} 段"
        )

    # ===== Step 3: Diarization（預設關閉；需要才開） =====
    want_spk = _want_diarization(ctx_text)
    if want_spk:
        segs, speakers = run_diarization(audio_path, tx["segments"], progress)
        tx["segments"] = segs
    else:
        segs = tx["segments"]
        speakers = {}
        await send_message("🧍 Speaker 分辨（diarization）預設不執行：本次依照『準確度優先＋穩定』設定先略過。若尼想要分講者，下次訊息加上：speaker / 說話者 / 分辨 speaker。")

    # Speaker 預填 (階段 A)
    if speakers and metadata.get("attendees"):
        sorted_s = sorted(speakers, key=lambda s: speakers[s]["duration_sec"], reverse=True)
        for i, spk in enumerate(sorted_s):
            speakers[spk]["display_name"] = (
                metadata["attendees"][i] if i < len(metadata["attendees"]) else spk
            )

    # Speaker 校正 (階段 B)
    if speakers and len(speakers) > 1:
        # Build representative quotes per speaker (方案1)
        quotes_by = build_speaker_quotes(tx["segments"], speakers, top_n=3)
        kept, ignored = filter_non_topic_speakers(speakers, quotes_by)

        preview = get_speaker_preview({k: speakers[k] for k in kept}) if kept else get_speaker_preview(speakers)
        sorted_s = kept if kept else sorted(speakers, key=lambda s: speakers[s]["duration_sec"], reverse=True)

        msg = f"🎤 偵測到 {len(speakers)} 位說話者"
        if ignored:
            msg += f"（已先忽略 {len(ignored)} 位：談話量少/零散/多為閒聊）"
        msg += f":\n{preview}\n\n"

        # show quotes for kept speakers only
        for spk in sorted_s:
            q = (quotes_by.get(spk) or {}).get("quotes", [])
            if not q:
                continue
            disp = speakers[spk].get("display_name", spk)
            msg += f"【{spk} → {disp}】\n"
            for i, it in enumerate(q, 1):
                msg += f"  {i}. ({_fmt_ts(it['start'])}-{_fmt_ts(it['end'])}) {it['text']}\n"
            msg += "\n"

        if metadata.get("attendees"):
            msg += "目前對應:\n"
            for spk in sorted_s:
                msg += f"  {spk} → {speakers[spk].get('display_name', spk)}\n"

        msg += "\n修改: 00=名稱, 01=名稱\n或 ok 確認（若要把被忽略的也加回來，回覆：include 02,03…）"

        await send_message(msg)
        sr = await ask_user("Speaker")

        # Optional: allow user to include ignored speakers back
        sr_l = (sr or "").strip().lower()
        if sr_l.startswith("include") and ignored:
            # parse include indices like: include 02,03
            inc = re.findall(r"\b\d+\b", sr_l)
            for idx in inc:
                for spk in ignored:
                    if idx in spk and spk not in sorted_s:
                        sorted_s.append(spk)
            # re-sort with newly included speakers
            sorted_s = sorted(sorted_s, key=lambda s: speakers[s]["duration_sec"], reverse=True)

        if sr_l not in ("ok", "跳過", "") and not sr_l.startswith("include"):
            for pair in sr.split(","):
                if "=" in pair:
                    idx, name = pair.split("=", 1)
                    for spk in speakers:
                        if idx.strip() in spk:
                            speakers[spk]["display_name"] = name.strip()
                            break

    for spk in speakers:
        speakers[spk].setdefault("display_name", spk)

    # ===== Step 4: LLM 摘要 =====
    spk_count = len(speakers) if speakers else 1
    tmpl = select_template(metadata.get("type", "business"), spk_count, tx["duration_sec"]/60, override=(metadata.get("template_override") or None))
    final_model = select_model(tx["duration_sec"]/60, metadata.get("model_pref"))

    await send_message(f"📝 {TEMPLATE_NAMES.get(tmpl, tmpl)} | {final_model}\n摘要中...")

    # Build transcript once (for local archive / glossary detection)
    plain = _build_transcript_plain(segs, speakers)
    trans_md = _build_transcript_md(segs, speakers)

    # Long recording optimization:
    # - DO NOT feed full transcript to the final LLM call
    # - chunk -> cheap model notes -> one final reduce with stronger model
    use_chunk = (tx["duration_sec"] >= 45 * 60) or (len(plain) >= 50000)

    try:
        if use_chunk:
            chunk_model = select_chunk_model(tx["duration_sec"]/60, metadata.get("model_pref"))
            await send_message(f"⏳ 長音檔模式：分段整理 → 整合\n  chunks: {chunk_model} → final: {final_model}")

            chunks = _chunk_segments_for_llm(segs, speakers, max_chars=12000, max_minutes=12)
            await send_message(f"🔪 已切成 {len(chunks)} 段（每段約 10~12 分鐘）")

            # Build template system prompt without embedding transcript
            tmpl_sys, metadata_block, glossary_md = build_system_prompt(tmpl, plain, metadata, speakers)

            import asyncio
            sem = asyncio.Semaphore(3)  # control concurrency to reduce rate-limit risk

            async def _summarize_one(i, ch):
                label = f"{i}/{len(chunks)} {ch['label']}"
                sys_c, usr_c = build_chunk_prompt(ch["text"], label, metadata, speakers)
                async with sem:
                    note = await _call_llm(chunk_model, sys_c, usr_c, send_message, max_tokens=1200)
                return i, label, note

            tasks = [asyncio.create_task(_summarize_one(i, ch)) for i, ch in enumerate(chunks, 1)]

            chunk_notes = [None] * len(chunks)
            done = 0
            for fut in asyncio.as_completed(tasks):
                i, label, note = await fut
                chunk_notes[i-1] = f"## {label}\n{note}"
                done += 1
                if done % 4 == 0 or done == len(chunks):
                    await send_message(f"…已完成 {done}/{len(chunks)} 段")

            chunk_notes_md = "\n\n".join([x for x in chunk_notes if x])
            sys_p, usr_m = build_reduce_prompt(tmpl_sys, metadata_block, chunk_notes_md, glossary_md)
            summary = await _call_llm(final_model, sys_p, usr_m, send_message, max_tokens=6000)

        else:
            sys_p, usr_m = build_summary_prompt(tmpl, plain, metadata, speakers)
            summary = await _call_llm(final_model, sys_p, usr_m, send_message, max_tokens=6000)

    except Exception as e:
        await send_message(f"⚠️ LLM 失敗: {e}\n上傳逐字稿...")
        summary = f"## 摘要失敗\n\n{e}"
    # ===== Step 5: 本地備份 =====
    out = CONFIG["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    name = (metadata.get("course_name") or "rec").replace("/", "-").replace(" ", "_")
    md_path = out / f"{metadata.get('date','x')}_{name}.md"
    md_path.write_text(f"{summary}\n\n---\n\n{trans_md}", encoding="utf-8")

    docx_path = _write_summary_docx(summary, metadata, out)

    # ===== Step 6: Notion =====
    await send_message("📤 上傳 Notion...")
    try:
        if metadata.get("type") == "emba":
            url = upload_emba(metadata, summary, '', tx["duration_sec"])
            label = "課堂摘要庫"
        else:
            metadata["action_items_text"] = _extract_action_items(summary)
            metadata["report_lines"] = _extract_report_lines(summary)
            url = upload_business(metadata, summary, '', tx["duration_sec"])
            label = "商務會談摘要DB"
        await send_message(f"✅ Done!\n📂 {label}\n🔗 {url}\n💾 {md_path}" + (f"\n📎 DOCX: {docx_path}" if docx_path else ''))
        if docx_path:
            await _send_docx_to_chat(send_message, docx_path, caption=f"{metadata.get('date','')} {metadata.get('course_name') or metadata.get('meeting_name') or '摘要'}")
    except Exception as e:
        await send_message(f"❌ Notion 失敗: {e}\n💾 {md_path}" + (f"\n📎 DOCX: {docx_path}" if docx_path else ''))
        if docx_path:
            await _send_docx_to_chat(send_message, docx_path, caption=f"{metadata.get('date','')} {metadata.get('course_name') or metadata.get('meeting_name') or '摘要'}")



# ============================================================
# Unified entry point (audio file OR cloud link message)
# ============================================================

async def handle_message(payload, send_message, ask_user, recording_time=None, pending_files=None, **kwargs):
    """Entry point that supports:
    - Telegram audio trigger: payload is local audio_path
    - Telegram text trigger: payload is message text containing Google Drive/OneDrive link

    Notes:
    - For text triggers, we download first, then reuse handle_audio_message.
    - kwargs are accepted for forward-compat with OpenClaw envelopes.
    """
    # Case 1: OpenClaw passes a dict envelope
    if isinstance(payload, dict):
        message_text = payload.get('text') or payload.get('message') or payload.get('message_text')
        audio_path = payload.get('audio_path') or payload.get('file_path')
        caption = payload.get('caption')
    else:
        message_text = kwargs.get('message_text') or kwargs.get('text') or ''
        caption = kwargs.get('caption') or ''
        audio_path = payload

    # If it's a real file path, process as audio
    try:
        if isinstance(audio_path, str) and audio_path and Path(audio_path).exists():
            return await handle_audio_message(
                audio_path,
                send_message,
                ask_user,
                recording_time=recording_time,
                pending_files=pending_files,
                message_text=message_text,
                caption=caption,
            )
    except Exception:
        pass

    # Otherwise treat as message text and look for URL
    text = ''
    if isinstance(audio_path, str) and audio_path and audio_path.startswith('http'):
        text = audio_path
    else:
        text = (caption or '') + "\n" + (message_text or '')

    url = _pick_first_url(text)
    if not url:
        # Avoid noisy auto-triggers (e.g., discord_message) when the message isn't an audio link.
        # If the user actually wants transcription, they'll paste a link or upload an audio file.
        return

    await send_message("🔗 收到雲端連結，正在下載音訊檔…")
    try:
        dl_path = _download_shared_audio(url, CONFIG["output_dir"] / "downloads")
    except Exception as e:
        await send_message(f"❌ 下載失敗：{e}\n\n請確認連結是『任何知道連結的人都可下載』，或直接把音訊檔丟到 Telegram 給我。")
        return

    await send_message(f"✅ 下載完成：{dl_path.name}\n開始轉錄整理…")
    return await handle_audio_message(
        str(dl_path),
        send_message,
        ask_user,
        recording_time=recording_time,
        pending_files=pending_files,
        message_text=text,
        caption=caption,
    )

# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys, asyncio
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if len(sys.argv) < 2:
        print("單檔: python lecture_pipeline.py <音訊> [YYYY-MM-DD] [HH:MM]")
        print("多檔: python lecture_pipeline.py --merge f1.m4a f2.m4a")
        sys.exit(1)

    async def send(m): print(f"\n💬 {m}")
    async def ask(q): return input(f"\n❓ {q}\n> ")

    if sys.argv[1] == "--merge":
        asyncio.run(handle_audio_message(sys.argv[2], send, ask, pending_files=sys.argv[2:]))
    else:
        rec = None
        if len(sys.argv) >= 3:
            d, t = sys.argv[2], sys.argv[3] if len(sys.argv) >= 4 else "12:00"
            rec = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
        asyncio.run(handle_audio_message(sys.argv[1], send, ask, rec))
