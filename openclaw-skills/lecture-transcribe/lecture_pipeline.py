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
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from transcribe import (
    transcribe_audio, run_diarization, get_audio_duration,
    merge_audio_files, get_speaker_preview,
)
from summary_prompts import (
    select_template, select_model, build_summary_prompt, TEMPLATE_NAMES,
)
from notion_upload import upload_emba, upload_business

logger = logging.getLogger(__name__)

CONFIG = {
    "schedule_path": Path(__file__).parent / "course_schedule.yaml",
    "output_dir": Path.home() / "whisperx-outputs",
}


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

async def _call_llm(model_id, system_prompt, user_message, send_message=None):
    """
    呼叫 LLM。優先走 OpenClaw routing，fallback 直接 API。
    """
    # 方式 1: OpenClaw 內建 (根據實際架構調整 import)
    try:
        from openclaw.llm import chat_completion
        resp = await chat_completion(
            model=model_id, system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=8000,
        )
        return resp.get("content", "")
    except ImportError:
        pass

    # 方式 2: Anthropic API 直接呼叫
    if "claude" in model_id or "anthropic" in model_id:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    # Fallback
    logger.warning(f"模型 {model_id} 無直接 API，fallback Claude")
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=8000,
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
    metadata = _infer_course(recording_time)

    if metadata["auto_detected"]:
        # EMBA 自動
        await send_message(
            f"📚 EMBA 課堂:\n"
            f"  {metadata['course_name']} / {metadata['professor']}\n"
            f"  {metadata['date']} 週{metadata['day_of_week']} / {dur_min:.0f}min\n\n"
            f"補充關鍵字? (逗號分隔 或 ok)"
        )
        kw = await ask_user("關鍵字")
        metadata["keywords"] = (
            [k.strip() for k in kw.split(",") if k.strip()]
            if kw.lower() not in ("ok", "跳過", "") else []
        )
        metadata["model_pref"] = None

    else:
        # 問類型
        await send_message(
            f"📝 收到錄音 ({metadata['date']} 週{metadata['day_of_week']}, {dur_min:.0f}min)\n\n"
            f"  1️⃣ 💼 商務會談\n  2️⃣ 📚 EMBA\n  3️⃣ 📋 其他"
        )
        tr = await ask_user("類型")

        if tr.strip() in ("2", "課堂", "emba"):
            metadata["type"] = "emba"
            await send_message("回覆: 課程名稱 / 教授 / 關鍵字(選填)")
            info = await ask_user("課程")
            parts = [p.strip() for p in info.split("/")]
            metadata["course_name"] = parts[0] if len(parts) > 0 else ""
            metadata["professor"] = parts[1] if len(parts) > 1 else ""
            metadata["keywords"] = (
                [k.strip() for k in parts[2].split(",") if k.strip()]
                if len(parts) > 2 else []
            )
            metadata["model_pref"] = None

        elif tr.strip() in ("1", "商務", "會議", ""):
            metadata["type"] = "business"
            await send_message(
                "💼 回覆 (/ 分隔):\n"
                "  主題 / 對象公司 / 類別(出差/來訪/線上) / 課別(WS/WQ/跨部門)\n"
                "  / 地點(選填) / 與會人員(選填) / 模型(選填)\n\n"
                "例: SUBARU規格討論 / SUBARU-JP / 來訪 / WS"
            )
            biz = await ask_user("會談資訊")
            p = [x.strip() for x in biz.split("/")]
            metadata["course_name"] = p[0] if len(p) > 0 else ""
            metadata["company"] = p[1] if len(p) > 1 else ""
            metadata["category"] = _norm_category(p[2]) if len(p) > 2 else ""
            metadata["department"] = _norm_dept(p[3]) if len(p) > 3 else ""
            metadata["location"] = p[4] if len(p) > 4 else ""
            metadata["attendees"] = (
                [a.strip() for a in p[5].split(",") if a.strip()]
                if len(p) > 5 else []
            )
            metadata["model_pref"] = p[6].strip() if len(p) > 6 else None
            metadata["keywords"] = []

        else:
            metadata["type"] = "other"
            await send_message("回覆: 名稱")
            n = await ask_user("名稱")
            metadata["course_name"] = n.strip() or "其他錄音"
            metadata["model_pref"] = None

    # ===== Step 2: 轉錄 =====
    await send_message("🎙️ 開始轉錄...")
    t0 = time.time()
    try:
        tx = transcribe_audio(audio_path, progress_cb=progress)
    except Exception as e:
        await send_message(f"❌ 轉錄失敗: {e}")
        return

    elapsed = time.time() - t0
    engine = tx.get("engine_used", "")
    ratio = tx["duration_sec"] / elapsed if elapsed > 0 else 0
    await send_message(
        f"✅ 轉錄完成 | {engine} | {elapsed:.0f}s ({ratio:.1f}x)\n"
        f"  {_fmt_dur(tx['duration_sec'])} / {len(tx['segments'])} 段"
    )

    # ===== Step 3: Diarization =====
    segs, speakers = run_diarization(audio_path, tx["segments"], progress)
    tx["segments"] = segs

    # Speaker 預填 (階段 A)
    if speakers and metadata.get("attendees"):
        sorted_s = sorted(speakers, key=lambda s: speakers[s]["duration_sec"], reverse=True)
        for i, spk in enumerate(sorted_s):
            speakers[spk]["display_name"] = (
                metadata["attendees"][i] if i < len(metadata["attendees"]) else spk
            )

    # Speaker 校正 (階段 B)
    if speakers and len(speakers) > 1:
        preview = get_speaker_preview(speakers)
        sorted_s = sorted(speakers, key=lambda s: speakers[s]["duration_sec"], reverse=True)
        msg = f"🎤 {len(speakers)} 位說話者:\n{preview}\n\n"

        if metadata.get("attendees"):
            msg += "目前對應:\n"
            for spk in sorted_s:
                msg += f"  {spk} → {speakers[spk].get('display_name', spk)}\n"
        msg += "\n修改: 00=名稱, 01=名稱\n或 ok 確認"

        await send_message(msg)
        sr = await ask_user("Speaker")

        if sr.lower() not in ("ok", "跳過", ""):
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
    tmpl = select_template(metadata.get("type", "business"), spk_count, tx["duration_sec"]/60)
    model = select_model(tx["duration_sec"]/60, metadata.get("model_pref"))

    await send_message(f"📝 {TEMPLATE_NAMES.get(tmpl, tmpl)} | {model}\n摘要中...")

    plain = _build_transcript_plain(segs, speakers)
    trans_md = _build_transcript_md(segs, speakers)
    sys_p, usr_m = build_summary_prompt(tmpl, plain, metadata, speakers)

    try:
        summary = await _call_llm(model, sys_p, usr_m, send_message)
    except Exception as e:
        await send_message(f"⚠️ LLM 失敗: {e}\n上傳逐字稿...")
        summary = f"## 摘要失敗\n\n{e}"

    # ===== Step 5: 本地備份 =====
    out = CONFIG["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    name = (metadata.get("course_name") or "rec").replace("/", "-").replace(" ", "_")
    md_path = out / f"{metadata.get('date','x')}_{name}.md"
    md_path.write_text(f"{summary}\n\n---\n\n{trans_md}", encoding="utf-8")

    # ===== Step 6: Notion =====
    await send_message("📤 上傳 Notion...")
    try:
        if metadata.get("type") == "emba":
            url = upload_emba(metadata, summary, trans_md, tx["duration_sec"])
            label = "課堂摘要庫"
        else:
            metadata["action_items_text"] = _extract_action_items(summary)
            url = upload_business(metadata, summary, trans_md, tx["duration_sec"])
            label = "商務會談摘要DB"
        await send_message(f"✅ Done!\n📂 {label}\n🔗 {url}\n💾 {md_path}")
    except Exception as e:
        await send_message(f"❌ Notion 失敗: {e}\n💾 {md_path}")


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
