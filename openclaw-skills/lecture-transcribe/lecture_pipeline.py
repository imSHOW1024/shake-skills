"""
lecture_pipeline.py — EMBA 課堂錄音 → Notion 課堂摘要庫 完整 Pipeline

流程:
  1. 接收音訊檔 (由 Telegram handler 呼叫)
  2. WhisperX 轉錄 + Diarization
  3. 辨識主講者 (說最多的 speaker)
  4. 透過 Telegram 向使用者確認/補充 metadata
  5. 產生 Markdown 格式逐字稿
  6. 上傳至 Notion DB (課堂摘要庫)

依賴:
  - whisperx, torch, pyannote.audio (見 install_whisperx.sh)
  - pyyaml, notion-client, python-telegram-bot
  - HF_TOKEN 環境變數 (pyannote diarization)
  - NOTION_TOKEN 環境變數 (Notion API)

位置: ~/openclaw-skills/lecture-transcribe/lecture_pipeline.py
"""

import os
import json
import time
import yaml
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 設定
# ============================================================

CONFIG = {
    "whisperx": {
        "model_size": "large-v3",     # 精度優先; 快速測試可改 "base"
        "device": "cpu",               # MPS 尚不穩定
        "compute_type": "int8",        # Apple Silicon CPU 最佳
        "batch_size": 8,               # M1 MAX 32GB 可開到 16
        "language": None,              # None = 自動偵測; 強制中文可設 "zh"
    },
    "diarization": {
        "min_speakers": 1,
        "max_speakers": 5,             # 課堂場景通常 1-3 人
    },
    "notion": {
        # 課堂摘要庫 Database ID (從 URL 擷取)
        "database_id": "f7fea4c19f1e4dd58e0da38dee21a2d8",
    },
    "schedule_path": Path(__file__).parent / "course_schedule.yaml",
    "output_dir": Path.home() / "whisperx-outputs",
}


# ============================================================
# 1. 課表自動推斷
# ============================================================

def load_schedule(path: Path) -> list:
    """載入課表 YAML"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("courses", [])


def infer_course_metadata(
    recording_date: Optional[datetime] = None,
    schedule_path: Optional[Path] = None,
) -> dict:
    """
    根據錄音日期/時間自動推斷課程資訊。
    回傳 dict: {name, professor, room, date, day_of_week}
    如果無法推斷，回傳空值讓使用者手動補。
    """
    if recording_date is None:
        recording_date = datetime.now()

    schedule_path = schedule_path or CONFIG["schedule_path"]
    courses = load_schedule(schedule_path)

    # Python: Monday=0, 週四=3, 週五=4, 週六=5
    weekday = recording_date.weekday()
    # YAML 裡 day: 4=週四, 5=週五, 6=週六
    # 轉換: Python weekday + 1 = ISO weekday (Mon=1)
    iso_weekday = weekday + 1  # Mon=1, Thu=4, Fri=5, Sat=6

    current_time = recording_date.strftime("%H:%M")

    matched = None
    for course in courses:
        if course["day"] != iso_weekday:
            continue
        # 允許前後 30 分鐘的彈性
        start_h, start_m = map(int, course["start"].split(":"))
        end_h, end_m = map(int, course["end"].split(":"))
        course_start = f"{start_h:02d}:{start_m - 30 if start_m >= 30 else 0:02d}"
        course_end = f"{end_h:02d}:{min(end_m + 30, 59):02d}"

        if course_start <= current_time <= course_end:
            matched = course
            break

    if matched:
        return {
            "course_name": matched["name"],
            "professor": matched["professor"],
            "room": matched.get("room", ""),
            "date": recording_date.strftime("%Y-%m-%d"),
            "day_of_week": ["一", "二", "三", "四", "五", "六", "日"][weekday],
            "auto_detected": True,
        }
    else:
        return {
            "course_name": "",
            "professor": "",
            "room": "",
            "date": recording_date.strftime("%Y-%m-%d"),
            "day_of_week": ["一", "二", "三", "四", "五", "六", "日"][weekday],
            "auto_detected": False,
        }


# ============================================================
# 2. WhisperX 轉錄 + Diarization
# ============================================================

def transcribe_audio(audio_path: str) -> dict:
    """
    WhisperX 轉錄 + 字級對齊 + 說話者辨識
    回傳: {segments, language, duration_sec, speakers_summary}
    """
    import whisperx

    cfg = CONFIG["whisperx"]
    hf_token = os.environ.get("HF_TOKEN", "")

    logger.info(f"開始轉錄: {audio_path}")
    logger.info(f"模型: {cfg['model_size']} | 裝置: {cfg['device']}")

    # Step 1: 轉錄
    t0 = time.time()
    model = whisperx.load_model(
        cfg["model_size"],
        cfg["device"],
        compute_type=cfg["compute_type"],
        language=cfg["language"],
    )
    result = model.transcribe(audio_path, batch_size=cfg["batch_size"])
    lang = result.get("language", "unknown")
    logger.info(f"轉錄完成 ({time.time()-t0:.1f}s), 語言={lang}")

    # Step 2: 字級對齊
    try:
        model_a, metadata = whisperx.load_align_model(
            language_code=lang, device=cfg["device"]
        )
        result = whisperx.align(
            result["segments"], model_a, metadata, audio_path, cfg["device"]
        )
        logger.info("字級對齊完成")
    except Exception as e:
        logger.warning(f"字級對齊失敗 ({lang}): {e}")

    # Step 3: Diarization
    speakers_summary = {}
    if hf_token:
        try:
            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=hf_token,
                device=cfg["device"],
            )
            diarize_segments = diarize_model(
                audio_path,
                min_speakers=CONFIG["diarization"]["min_speakers"],
                max_speakers=CONFIG["diarization"]["max_speakers"],
            )
            result = whisperx.assign_word_speakers(diarize_segments, result)
            logger.info("Diarization 完成")

            # 統計每個 speaker 的發言時長
            speakers_summary = _calc_speaker_stats(result.get("segments", []))
        except Exception as e:
            logger.warning(f"Diarization 失敗: {e}")
    else:
        logger.warning("未設定 HF_TOKEN，跳過 Diarization")

    segments = result.get("segments", [])
    duration = segments[-1]["end"] if segments else 0

    return {
        "segments": segments,
        "language": lang,
        "duration_sec": duration,
        "speakers_summary": speakers_summary,
    }


def _calc_speaker_stats(segments: list) -> dict:
    """統計各 speaker 發言時長，辨識主講者"""
    stats = {}
    for seg in segments:
        spk = seg.get("speaker", "UNKNOWN")
        dur = seg.get("end", 0) - seg.get("start", 0)
        if spk not in stats:
            stats[spk] = {"duration_sec": 0, "segment_count": 0}
        stats[spk]["duration_sec"] += dur
        stats[spk]["segment_count"] += 1

    # 標記主講者 (說最久的人)
    if stats:
        main_speaker = max(stats, key=lambda s: stats[s]["duration_sec"])
        for spk in stats:
            stats[spk]["is_main_speaker"] = (spk == main_speaker)
            stats[spk]["role"] = "教授(推測)" if spk == main_speaker else "其他"

    return stats


# ============================================================
# 3. Markdown 生成
# ============================================================

def generate_markdown(
    transcription: dict,
    metadata: dict,
    user_notes: str = "",
) -> str:
    """
    產生結構化 Markdown，適合 Notion 頁面 body。
    """
    segments = transcription["segments"]
    speakers = transcription.get("speakers_summary", {})
    lang = transcription.get("language", "")
    duration = transcription.get("duration_sec", 0)

    # 找出主講者 ID
    main_spk = None
    for spk, info in speakers.items():
        if info.get("is_main_speaker"):
            main_spk = spk
            break

    # --- Header ---
    lines = []
    lines.append(f"# {metadata.get('course_name', '未知課程')} — 課堂逐字稿")
    lines.append("")
    lines.append(f"- **日期**: {metadata.get('date', '')} (週{metadata.get('day_of_week', '')})")
    lines.append(f"- **教授**: {metadata.get('professor', '未知')}")
    if metadata.get("room"):
        lines.append(f"- **教室**: {metadata['room']}")
    lines.append(f"- **錄音長度**: {_format_duration(duration)}")
    lines.append(f"- **偵測語言**: {lang}")

    if user_notes:
        lines.append(f"- **備註**: {user_notes}")

    # --- Speaker 統計 ---
    if speakers:
        lines.append("")
        lines.append("## 說話者統計")
        lines.append("")
        lines.append("| 說話者 | 角色 | 發言時長 | 片段數 |")
        lines.append("|--------|------|----------|--------|")
        for spk, info in sorted(
            speakers.items(),
            key=lambda x: x[1]["duration_sec"],
            reverse=True,
        ):
            role = info.get("role", "")
            dur = _format_duration(info["duration_sec"])
            cnt = info["segment_count"]
            marker = " 🎓" if info.get("is_main_speaker") else ""
            lines.append(f"| {spk}{marker} | {role} | {dur} | {cnt} |")

    # --- 逐字稿 ---
    lines.append("")
    lines.append("## 逐字稿")
    lines.append("")

    current_speaker = None
    for seg in segments:
        spk = seg.get("speaker", "???")
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)

        if not text:
            continue

        # 換說話者時加標題
        if spk != current_speaker:
            current_speaker = spk
            role_tag = "🎓 教授" if spk == main_spk else spk
            lines.append("")
            lines.append(f"**{role_tag}** `[{_format_timestamp(start)}]`")
            lines.append("")

        lines.append(f"{text}")

    # --- Keywords placeholder ---
    lines.append("")
    lines.append("## 關鍵字")
    lines.append("")
    if metadata.get("keywords"):
        lines.append(", ".join(metadata["keywords"]))
    else:
        lines.append("*(待補充)*")

    lines.append("")
    lines.append("---")
    lines.append(f"*由 小龍女 (OpenClaw) 自動轉錄產生 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ============================================================
# 4. Notion 上傳
# ============================================================

def upload_to_notion(
    metadata: dict,
    markdown_content: str,
    transcription: dict,
) -> str:
    """
    上傳至 Notion 課堂摘要庫。
    回傳: Notion page URL

    Notion DB 預期欄位 (需根據實際 DB 欄位調整):
      - 課程名稱 (Title)
      - 日期 (Date)
      - 教授 (Rich Text / Select)
      - 關鍵字 (Multi-select)
      - 學期 (Select)
      - 狀態 (Status / Select)
      - 錄音長度 (Rich Text)
      - 逐字稿 (Page body as Markdown blocks)
    """
    from notion_client import Client

    notion_token = os.environ.get("NOTION_TOKEN", "")
    if not notion_token:
        raise RuntimeError("未設定 NOTION_TOKEN 環境變數")

    notion = Client(auth=notion_token)
    db_id = CONFIG["notion"]["database_id"]

    duration = transcription.get("duration_sec", 0)

    # ---- 建立 Properties ----
    # ⚠️ 以下 property name 需與你的 Notion DB 實際欄位名稱完全一致
    # 第一次跑完後，根據實際 DB schema 調整
    properties = {
        # Title property (通常叫 "名稱" 或 "Name")
        "名稱": {
            "title": [
                {
                    "text": {
                        "content": f"{metadata.get('course_name', '未知課程')} {metadata.get('date', '')}"
                    }
                }
            ]
        },
    }

    # Date property
    if metadata.get("date"):
        properties["日期"] = {
            "date": {"start": metadata["date"]}
        }

    # Rich Text properties
    if metadata.get("professor"):
        properties["教授"] = {
            "rich_text": [{"text": {"content": metadata["professor"]}}]
        }

    properties["錄音長度"] = {
        "rich_text": [{"text": {"content": _format_duration(duration)}}]
    }

    # Multi-select: 關鍵字
    if metadata.get("keywords"):
        properties["關鍵字"] = {
            "multi_select": [{"name": kw} for kw in metadata["keywords"]]
        }

    # ---- 建立 Page Body (Markdown → Notion Blocks) ----
    # Notion API 不直接吃 Markdown，需轉成 blocks
    # 這裡用簡化版：把 markdown 切段塞進 paragraph blocks
    # 進階可用 martian 或 notion-md-converter 套件
    children = _markdown_to_notion_blocks(markdown_content)

    # ---- 建立頁面 ----
    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=children[:100],  # Notion API 單次上限 100 blocks
    )

    page_url = page.get("url", "")
    page_id = page.get("id", "")

    # 如果超過 100 blocks，分批 append
    if len(children) > 100:
        for i in range(100, len(children), 100):
            batch = children[i : i + 100]
            notion.blocks.children.append(block_id=page_id, children=batch)
            logger.info(f"追加 blocks: {i}-{i+len(batch)}")

    logger.info(f"Notion 頁面建立完成: {page_url}")
    return page_url


def _markdown_to_notion_blocks(md: str) -> list:
    """
    簡易 Markdown → Notion blocks 轉換
    支援: h1, h2, h3, bullet, paragraph, divider, table (基本)
    進階需求可改用 martian 套件: pip install martian
    """
    blocks = []
    lines = md.split("\n")

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        # Headings
        if stripped.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]
                },
            })
        elif stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]
                },
            })
        elif stripped.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]
                },
            })
        # Divider
        elif stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # Bullet
        elif stripped.startswith("- "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": _parse_rich_text(stripped[2:])
                },
            })
        # Table row (skip header separator)
        elif stripped.startswith("|") and not stripped.replace("|", "").replace("-", "").strip() == "":
            # 表格在 Notion 處理較複雜，先轉為文字段落
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": stripped}}]
                },
            })
        # Regular paragraph
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": _parse_rich_text(stripped)
                },
            })

    return blocks


def _parse_rich_text(text: str) -> list:
    """
    簡易 rich text 解析。
    處理 **bold** 和 `code` 標記。
    """
    import re

    segments = []
    # 簡化: 先處理整段文字，不拆 inline 格式
    # 完整版應用 regex 拆分 bold / italic / code
    # Notion rich_text 單段上限 2000 字元
    MAX_LEN = 2000

    for i in range(0, len(text), MAX_LEN):
        chunk = text[i : i + MAX_LEN]
        segments.append({
            "type": "text",
            "text": {"content": chunk},
        })

    return segments


# ============================================================
# 5. Telegram 互動流程 (由 OpenClaw handler 呼叫)
# ============================================================

async def handle_audio_message(
    audio_path: str,
    send_message,       # async callable: Telegram 回訊息
    ask_user,           # async callable: 問使用者問題，回傳回答
    recording_time: Optional[datetime] = None,
):
    """
    完整流程入口，由 OpenClaw 的 Telegram handler 呼叫。

    Parameters:
        audio_path:     下載好的音訊檔路徑
        send_message:   async fn(text) → 傳訊息給使用者
        ask_user:       async fn(question) → str 使用者回覆
        recording_time: 錄音時間 (若 None 則用當前時間)
    """
    # ---- Step 1: 自動推斷 metadata ----
    metadata = infer_course_metadata(recording_time)

    if metadata["auto_detected"]:
        await send_message(
            f"📚 自動偵測到課程:\n"
            f"  課程: {metadata['course_name']}\n"
            f"  教授: {metadata['professor']}\n"
            f"  日期: {metadata['date']} (週{metadata['day_of_week']})\n"
            f"\n正確嗎? 可以直接補充關鍵字，或輸入修正資訊。\n"
            f"(直接回覆關鍵字，用逗號分隔；或回 'ok' 跳過)"
        )
    else:
        await send_message(
            f"📚 無法自動判斷課程 (日期: {metadata['date']} 週{metadata['day_of_week']})\n"
            f"請告訴我:\n"
            f"1. 課程名稱\n"
            f"2. 教授姓名\n"
            f"(格式: 課程名稱 / 教授姓名)"
        )
        reply = await ask_user("等待課程資訊...")
        if "/" in reply:
            parts = reply.split("/")
            metadata["course_name"] = parts[0].strip()
            metadata["professor"] = parts[1].strip() if len(parts) > 1 else ""
        else:
            metadata["course_name"] = reply.strip()

    # 關鍵字
    kw_reply = await ask_user("補充關鍵字? (逗號分隔，或 'ok' 跳過)")
    if kw_reply.lower() not in ("ok", "跳過", "skip", ""):
        metadata["keywords"] = [kw.strip() for kw in kw_reply.split(",") if kw.strip()]
    else:
        metadata["keywords"] = []

    # ---- Step 2: WhisperX 轉錄 ----
    await send_message("🎙️ 開始轉錄，large-v3 模型載入中... (預計 3-10 分鐘)")
    t0 = time.time()

    try:
        transcription = transcribe_audio(audio_path)
    except Exception as e:
        await send_message(f"❌ 轉錄失敗: {e}")
        return

    elapsed = time.time() - t0
    n_seg = len(transcription["segments"])
    dur = _format_duration(transcription["duration_sec"])
    await send_message(
        f"✅ 轉錄完成!\n"
        f"  耗時: {elapsed:.0f}s\n"
        f"  片段: {n_seg} 段\n"
        f"  音訊長度: {dur}\n"
        f"  語言: {transcription['language']}"
    )

    # 顯示 speaker 統計
    if transcription["speakers_summary"]:
        stats_msg = "🎤 說話者統計:\n"
        for spk, info in sorted(
            transcription["speakers_summary"].items(),
            key=lambda x: x[1]["duration_sec"],
            reverse=True,
        ):
            role = "🎓教授" if info.get("is_main_speaker") else "  其他"
            d = _format_duration(info["duration_sec"])
            stats_msg += f"  {role} ({spk}): {d} / {info['segment_count']}段\n"
        await send_message(stats_msg)

    # ---- Step 3: 生成 Markdown ----
    user_notes = ""  # 可擴充: 讓使用者補充備註
    markdown = generate_markdown(transcription, metadata, user_notes)

    # 本地備份
    output_dir = CONFIG["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = metadata.get("date", "unknown")
    course_str = metadata.get("course_name", "unknown")
    md_path = output_dir / f"{date_str}_{course_str}.md"
    md_path.write_text(markdown, encoding="utf-8")
    logger.info(f"Markdown 已存: {md_path}")

    # ---- Step 4: 上傳 Notion ----
    await send_message("📤 上傳至 Notion 課堂摘要庫...")
    try:
        page_url = upload_to_notion(metadata, markdown, transcription)
        await send_message(
            f"✅ 已上傳至 Notion!\n"
            f"🔗 {page_url}\n"
            f"\n本地備份: {md_path}"
        )
    except Exception as e:
        await send_message(
            f"❌ Notion 上傳失敗: {e}\n"
            f"Markdown 已存至本地: {md_path}"
        )


# ============================================================
# 6. CLI 模式 (手動測試用)
# ============================================================

if __name__ == "__main__":
    import sys
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if len(sys.argv) < 2:
        print("用法: python lecture_pipeline.py <音訊檔> [YYYY-MM-DD] [HH:MM]")
        print("範例: python lecture_pipeline.py lecture.mp3 2026-03-07 14:30")
        sys.exit(1)

    audio_file = sys.argv[1]
    rec_time = None

    if len(sys.argv) >= 3:
        date_str = sys.argv[2]
        time_str = sys.argv[3] if len(sys.argv) >= 4 else "12:00"
        rec_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

    # CLI 模擬 Telegram 互動
    async def cli_send(msg):
        print(f"\n💬 {msg}")

    async def cli_ask(question):
        return input(f"\n❓ {question}\n> ")

    asyncio.run(handle_audio_message(audio_file, cli_send, cli_ask, rec_time))
