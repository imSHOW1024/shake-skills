from __future__ import annotations

"""
notion_upload.py — Notion 雙 DB 上傳

支援:
  - 課堂摘要DB (EMBA)
  - 商務會談摘要DB (商務)
  - 自動讀取 schema 對齊欄位
  - Toggle heading 收合逐字稿
"""

import os
import logging
import re
import urllib.parse
from datetime import datetime, date
from typing import Optional, Tuple

from icons import notion_service_emoji, notion_emoji_mention, notion_model_emoji

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "emba": {
        "database_id": "f7fea4c19f1e4dd58e0da38dee21a2d8",
        "name": "課堂摘要庫",
    },
    "business": {
        "database_id": "158465efa6f44fb99171f48cde34f5b2",
        "name": "商務會談摘要DB",
    },
}


def _get_notion_client():
    from notion_client import Client
    token = os.environ.get("NOTION_API_KEY", "")
    if not token:
        raise RuntimeError("NOTION_API_KEY 未設定")
    return Client(auth=token)


def _resolve_parent_target(notion, db_id: str) -> Tuple[dict, dict, Optional[str]]:
    """Resolve the exact Notion parent payload for writes.

    Newer Notion databases expose one or more `data_sources`; page creation should
    target the data source explicitly. We still keep the enclosing database id for
    post-write validation and legacy fallback.
    """
    db = notion.databases.retrieve(db_id)
    data_sources = (db or {}).get("data_sources") or []
    if data_sources:
        ds_id = (data_sources[0] or {}).get("id")
        if ds_id:
            return {"data_source_id": ds_id}, db, ds_id
    return {"database_id": db_id}, db, None


def _retrieve_schema(notion, db_id: str) -> dict:
    """Return property schema for a Notion database.

    Supports both legacy API (database.properties) and newer API where
    databases include `data_sources` and properties live on the data source.
    """
    parent_payload, db, ds_id = _resolve_parent_target(notion, db_id)

    # Legacy
    if isinstance(db, dict) and "properties" in db:
        return {name: prop.get("type") for name, prop in db["properties"].items()}

    # New API (databases -> data_sources)
    if ds_id:
        ds = notion.data_sources.retrieve(ds_id)
        if isinstance(ds, dict) and "properties" in ds:
            return {name: prop.get("type") for name, prop in ds["properties"].items()}

    raise KeyError(f"Unable to read schema for database_id={db_id}. parent={parent_payload} Keys={list((db or {}).keys())}")


def validate_notion_schema(db_type: str = "emba") -> dict:
    notion = _get_notion_client()
    db_id = DB_CONFIG[db_type]["database_id"]
    schema = _retrieve_schema(notion, db_id)
    logger.info(f"Notion [{db_type}] schema: {schema}")
    return schema


def _preview_title(db_type: str, metadata: Optional[dict] = None) -> str:
    metadata = metadata or {}
    if db_type == "business":
        meeting = metadata.get("meeting_name") or metadata.get("company") or metadata.get("target_company") or "未知會談"
        date = metadata.get("date") or ""
        return f"{meeting} {date}".strip()
    course = metadata.get("course_name") or metadata.get("title") or metadata.get("meeting_name") or "未知課程"
    date = metadata.get("date") or ""
    return f"{course} {date}".strip()


def _parent_matches_expected(parent: dict, expected_db_id: str, expected_ds_id: Optional[str] = None) -> bool:
    parent = parent or {}
    actual_db_id = (parent.get("database_id") or "").replace('-', '')
    actual_ds_id = (parent.get("data_source_id") or "").replace('-', '')
    expected_db_norm = (expected_db_id or '').replace('-', '')
    expected_ds_norm = (expected_ds_id or '').replace('-', '')
    db_ok = bool(expected_db_norm) and actual_db_id == expected_db_norm
    ds_ok = (not expected_ds_norm) or actual_ds_id == expected_ds_norm
    return bool(db_ok and ds_ok)


def preview_notion_write(db_type: str = "emba", metadata: Optional[dict] = None, page_id: Optional[str] = None) -> dict:
    """Read-only dry-run preview for a planned Notion write.

    Use this before uploads/overwrites to surface the exact target DB/data source,
    the inferred title, and whether an existing page lives in the expected parent.
    """
    notion = _get_notion_client()
    db_id = DB_CONFIG[db_type]["database_id"]
    parent_payload, _db, ds_id = _resolve_parent_target(notion, db_id)
    schema = _retrieve_schema(notion, db_id)
    title_field = next((k for k, v in schema.items() if v == "title"), "名稱")

    preview = {
        "db_type": db_type,
        "database_id": db_id,
        "data_source_id": ds_id,
        "parent_payload": parent_payload,
        "title_field": title_field,
        "preview_title": _preview_title(db_type, metadata),
        "schema_fields": sorted(schema.keys()),
        "metadata": metadata or {},
    }

    if page_id:
        page = notion.pages.retrieve(page_id=page_id)
        parent = (page or {}).get("parent") or {}
        preview.update({
            "page_id": page_id,
            "page_parent": parent,
            "page_parent_matches_expected": _parent_matches_expected(parent, db_id, ds_id),
        })
    return preview


def upload_to_notion(metadata, summary, transcript_text, transcription) -> str:
    record_type = metadata.get("type", "emba")
    if record_type in ("business", "meeting"):
        return _upload_business(metadata, summary, transcript_text, transcription)
    else:
        return _upload_emba(metadata, summary, transcript_text, transcription)


def _fmt_dur(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _infer_tw_semester(date_str: str) -> str:
    """Infer Taiwan/ROC-style semester label like '114-2' from ISO date.

    Assumptions (common university schedule):
      - Academic year starts in Aug.
      - Term 1: Aug–Jan
      - Term 2: Feb–Jul
      - Year is ROC year (Gregorian year - 1911) of the *academic year*.

    Examples:
      - 2026-03-13 -> 114-2 (AY 2025/2026, spring)
      - 2026-10-01 -> 115-1 (AY 2026/2027, fall)
    """
    if not (date_str or '').strip():
        return ''
    try:
        d = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except Exception:
        return ''

    # Academic year label
    if d.month >= 8:
        ay_gregorian = d.year
        term = 1
    elif d.month == 1:
        ay_gregorian = d.year - 1
        term = 1
    else:  # Feb–Jul
        ay_gregorian = d.year - 1
        term = 2

    roc_year = ay_gregorian - 1911
    return f"{roc_year}-{term}"


_DEF_WEEK1_DATE = date(2026, 2, 23)


def _infer_course_week(date_str: str) -> Optional[int]:
    """Infer course week number using 2026-02-23 as week 1 start."""
    if not (date_str or '').strip():
        return None
    try:
        d = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except Exception:
        return None
    delta_days = (d - _DEF_WEEK1_DATE).days
    if delta_days < 0:
        return None
    return delta_days // 7 + 1


def _extract_keywords_from_summary(summary: str) -> list[str]:
    """Extract keywords from the summary body.

    Priority:
    1) The dedicated '### 關鍵字' section
    2) Fallback to inline comma-separated values / bullets under that section
    """
    if not (summary or '').strip():
        return []

    lines = summary.splitlines()
    capture = False
    raw_items = []

    for line in lines:
        s = (line or '').strip()
        if not capture:
            if s.startswith('### ') and '關鍵字' in s:
                capture = True
            continue

        if s.startswith('### '):
            break
        if not s:
            continue

        s = re.sub(r'^[-*]\s*', '', s).strip()
        if not s:
            continue

        parts = [p.strip() for p in re.split(r'[、,，/｜|；;]+', s) if p.strip()]
        raw_items.extend(parts)

    out = []
    seen = set()
    for item in raw_items:
        item = re.sub(r'^關鍵字\s*[:：]\s*', '', item).strip()
        item = item.strip('「」"[]()（）')
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item[:100])
    return out[:20]


def _set_property_by_schema(props: dict, schema: dict, field: str, value):
    """Set a Notion property using the existing schema type."""
    if field not in schema or value in (None, '', []):
        return

    t = schema.get(field)
    if t == 'select':
        props[field] = {'select': {'name': str(value)}}
    elif t == 'multi_select':
        vals = value if isinstance(value, list) else [value]
        props[field] = {'multi_select': [{'name': str(v).strip()} for v in vals if str(v).strip()]}
    elif t == 'number':
        try:
            props[field] = {'number': int(value)}
        except Exception:
            return
    else:
        text = value if isinstance(value, str) else ', '.join(str(v) for v in value)
        props[field] = _rich_text_prop(text)


# ============================================================
# EMBA
# ============================================================

def _summary_has_workflow_footer(summary: str) -> bool:
    text = (summary or '').strip()
    return '作業路徑說明' in text



def _strip_workflow_footer_markdown(summary: str) -> str:
    text = summary or ''
    patterns = [
        r'\n---\s*\n\s*###\s*(?::[\w-]+:)?\s*作業路徑說明[\s\S]*$',
        r'\n###\s*(?::[\w-]+:)?\s*作業路徑說明[\s\S]*$',
        r'\n##\s*(?::[\w-]+:)?\s*作業路徑說明[\s\S]*$',
    ]
    for pat in patterns:
        text = re.sub(pat, '', text, flags=re.I)
    return text.rstrip() + '\n'



def _upload_emba(metadata, summary, transcript_text, transcription):
    notion = _get_notion_client()
    db_id = DB_CONFIG["emba"]["database_id"]
    schema = validate_notion_schema("emba")
    duration = transcription.get("duration_sec", 0)
    course = metadata.get("course_name", "未知課程")
    date = metadata.get("date", "")

    props = {}
    title_field = next((k for k, v in schema.items() if v == "title"), "名稱")
    props[title_field] = _title_prop(f"{course} {date}")

    if "日期" in schema and date:
        props["日期"] = {"date": {"start": date}}
    for field, val in [("教授", metadata.get("professor", "")), ("錄音長度", _fmt_dur(duration))]:
        if field in schema and val:
            t = schema.get(field)
            if t == "select":
                props[field] = {"select": {"name": str(val)}}
            elif t == "multi_select":
                props[field] = {"multi_select": [{"name": v.strip()} for v in str(val).split(",") if v.strip()]}
            else:
                props[field] = _rich_text_prop(str(val))
    extracted_keywords = _extract_keywords_from_summary(summary)
    merged_keywords = []
    seen_keywords = set()
    for kw in (metadata.get("keywords") or []) + extracted_keywords:
        k = str(kw).strip()
        if not k:
            continue
        kk = k.lower()
        if kk in seen_keywords:
            continue
        seen_keywords.add(kk)
        merged_keywords.append(k)

    if "關鍵字" in schema and merged_keywords:
        _set_property_by_schema(props, schema, "關鍵字", merged_keywords)
    if "關鍵字標籤" in schema and merged_keywords:
        _set_property_by_schema(props, schema, "關鍵字標籤", merged_keywords)
    if "學期" in schema:
        sem = _infer_tw_semester(date)
        if sem:
            _set_property_by_schema(props, schema, "學期", sem)
    if "週次" in schema:
        week_no = _infer_course_week(date)
        if week_no:
            if schema.get("週次") == "number":
                _set_property_by_schema(props, schema, "週次", week_no)
            else:
                _set_property_by_schema(props, schema, "週次", f"第{week_no}週")

    summary_body = _strip_workflow_footer_markdown(summary)
    children = _md_to_blocks(summary_body)
    children += _workflow_footer_blocks(metadata)
    return _create_page(notion, db_id, props, children)


# ============================================================


# ============================================================
# Obsidian 連結區塊（EMBA 頁面底部）
# ============================================================

_OBSIDIAN_VAULT = "小龍女知識庫"
_COURSE_TO_DIR = {
    "跨文化交流與研習": "跨文化交流與研習",
    "企業危機管理":     "企業危機管理",
    "企業研究方法":     "企業研究方法",
    "全球台商個案研討": "全球台商個案研討",
    "消費者行為":       "消費者行為",
    "科技與人文講座":   "科技與人文講座",
}


def _obsidian_link_blocks(metadata: dict) -> list:
    """Return Notion blocks with Obsidian deep-link to the corresponding lecture note."""
    course = metadata.get("course_name", "")
    date_str = metadata.get("date", "")

    course_dir = _COURSE_TO_DIR.get(course, course)
    # Build expected filename (matches lecture_pipeline.py convention)
    fname = f"{date_str}_{course}.md" if date_str else f"{course}.md"
    vault_rel = f"EMBA/02 每週課堂筆記/{course_dir}/{fname}"
    obsidian_uri = (
        f"obsidian://open?vault={urllib.parse.quote(_OBSIDIAN_VAULT)}"
        f"&file={urllib.parse.quote(vault_rel)}"
    )

    course_file_rel = f"EMBA/01 課程總覽/{course}.md"
    course_uri = (
        f"obsidian://open?vault={urllib.parse.quote(_OBSIDIAN_VAULT)}"
        f"&file={urllib.parse.quote(course_file_rel)}"
    )
    semester_uri = (
        f"obsidian://open?vault={urllib.parse.quote(_OBSIDIAN_VAULT)}"
        f"&file={urllib.parse.quote('EMBA/01 課程總覽/114-2 課程總覽.md')}"
    )

    return [
        {"object": "block", "type": "divider", "divider": {}},
        _heading_block(3, "🗂 Obsidian 知識庫連結"),
        {
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": "📓 本堂課堂筆記", "link": {"url": obsidian_uri}},
                 "annotations": {"bold": True, "color": "blue"}},
                {"type": "text", "text": {"content": f"　{vault_rel}"}},
            ]}
        },
        {
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": "📚 課程主檔", "link": {"url": course_uri}},
                 "annotations": {"color": "blue"}},
                {"type": "text", "text": {"content": f"　[[{course}]]"},
                 "annotations": {"code": True}},
            ]}
        },
        {
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": "📅 學期總覽", "link": {"url": semester_uri}},
                 "annotations": {"color": "blue"}},
                {"type": "text", "text": {"content": "　[[114-2 課程總覽]]"},
                 "annotations": {"code": True}},
            ]}
        },
    ]


# ============================================================
# 作業流程路徑 footer（全模板 / 全 DB 共用固定段落）
# ============================================================

def _workflow_footer_blocks(metadata: Optional[dict] = None) -> list:
    """動態產生所有摘要頁最下方的作業流程路徑說明。

    格式與 lecture_pipeline._append_summary_footer() 完全對齊：
    - 灰色斜體 bullet list
    - 支援 indent_level=1 縮排子層次（⚙️ 階段子項目）
    - ⚙️ Final 詳細資訊：無論是否 chunked 均顯示
    - 最後免責聲明固定使用 quote block 呈現
    """
    metadata = metadata or {}
    proc = metadata.get("process_summary") or {}
    import re as _re

    def _parse(text: str) -> list:
        """將 **bold** 包裹的文字解析為 Notion rich_text（含 gray italic + bold）。"""
        segs = []
        for i, part in enumerate(_re.split(r'\*\*(.+?)\*\*', text)):
            if not part:
                continue
            ann = {"italic": True, "color": "gray"}
            if i % 2 == 1:  # 被 ** 包裹 → bold
                ann["bold"] = True
            segs.append({"type": "text", "text": {"content": part}, "annotations": ann})
        if not segs:
            segs = [{"type": "text", "text": {"content": ""}, "annotations": {"italic": True, "color": "gray"}}]
        return segs

    def _bl(text: str, indent: int = 0) -> dict:
        """gray italic bulleted_list_item；indent>0 時前面加 → 前綴（Notion API 建立時不支援 indent 寫入）。"""
        prefix = "  " * indent + "→ " if indent else ""
        item = {"object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _parse(prefix + text)}}
        return item

    def _bl_rich(rich_text: list) -> dict:
        """直接接收 rich_text list 的 gray italic bulleted_list_item。"""
        return {"object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich_text}}

    def _text(content: str, *, bold: bool = False) -> dict:
        return {
            "type": "text",
            "text": {"content": content},
            "annotations": {
                "bold": bold,
                "italic": True,
                "strikethrough": False,
                "underline": False,
                "code": False,
                "color": "gray",
            },
        }

    def _emoji_with_gray(emoji_rt: Optional[dict], *, bold: bool = False) -> Optional[dict]:
        if not emoji_rt:
            return None
        r = dict(emoji_rt)
        r["annotations"] = {
            "bold": bold,
            "italic": True,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "gray",
        }
        return r

    def _model_line(label: str, model_id: str, suffix: str = '', indent: int = 1) -> dict:
        prefix = "  " * indent + "→ " if indent else ""
        rich = [_text(prefix)]
        emoji_rt = _emoji_with_gray(notion_model_emoji(model_id), bold=True)
        if emoji_rt:
            rich.append(emoji_rt)
            rich.append(_text(' '))
        rich.append(_text(f"{label}{model_id}{suffix}", bold=True))
        return _bl_rich(rich)

    def _model_chain_line(label: str, model_ids: list[str], indent: int = 1) -> dict:
        prefix = "  " * indent + "→ " if indent else ""
        rich = [_text(prefix), _text(label, bold=True)]
        for idx, model_id in enumerate(model_ids):
            rich.append(_text(' ' if idx == 0 else ' → '))
            emoji_rt = _emoji_with_gray(notion_model_emoji(model_id), bold=True)
            if emoji_rt:
                rich.append(emoji_rt)
                rich.append(_text(' '))
            rich.append(_text(model_id, bold=True))
        return _bl_rich(rich)

    def _quote_disclaimer(text: str) -> dict:
        """Disclaimer quote block supporting custom emoji mentions."""
        import re as _re2
        segs = []
        parts = _re2.split(r'(:[\w-]+:)', text)
        for part in parts:
            if not part:
                continue
            if _re2.match(r'^:[\w-]+:$', part):
                emoji_key = part[1:-1]
                emoji_name = 'openclaw-dark' if emoji_key == 'openclaw-color' else emoji_key
                emoji_mention = notion_emoji_mention(emoji_name)
                if emoji_mention:
                    emoji_mention['annotations'] = {
                        'bold': False, 'italic': False, 'color': 'default',
                        'strikethrough': False, 'underline': False, 'code': False,
                    }
                    segs.append(emoji_mention)
            else:
                for j, chunk in enumerate(_re2.split(r'\*\*(.+?)\*\*', part)):
                    if not chunk:
                        continue
                    ann = {'italic': False, 'bold': False, 'color': 'default',
                          'strikethrough': False, 'underline': False, 'code': False}
                    segs.append({
                        'type': 'text',
                        'text': {'content': chunk},
                        'annotations': ann,
                    })
        return {
            'object': 'block',
            'type': 'quote',
            'quote': {
                'rich_text': segs,
                'color': 'default',
            }
        }

    items = []

    # ── 1) 來源取得 ─────────────────────────────────────────
    cloud = proc.get("downloaded_from_cloud")
    src = {"gdrive": "Google Drive", "onedrive": "OneDrive"}.get(
        proc.get("cloud_source", "").lower(), "雲端")
    audio_format = proc.get("audio_format") or (
        metadata.get("audio_format") or ""
    )
    fmt_str = f"（{audio_format} 格式）" if audio_format else ""
    if cloud:
        items.append(_bl(f"來源取得：{src} 雲端 .{audio_format or '音訊'} 檔下載後處理"))
    else:
        items.append(_bl(f"來源取得：本機 / 既有音訊檔{fmt_str}直接處理"))

    # ── 2) 參考資料整合（若有）─────────────────────────────
    refs = proc.get("reference_sources") or []
    if refs:
        sl = "、".join(refs[:6])
        more = f" 等 {len(refs)} 項" if len(refs) > 6 else f"（共 {len(refs)} 項）"
        items.append(_bl(f"參考資料整合：本次納入參考來源{more}：{sl}，並與逐字稿交叉校對後再整理摘要。"))

    # ── 3) 音訊前處理 ──────────────────────────────────────
    tool = proc.get("preprocess_tool", "ffmpeg")
    desc = proc.get("preprocess_desc", "16kHz 單聲道正規化與 loudnorm 音量校正")
    items.append(_bl(f"音訊前處理：使用 **{tool}** 進行 {desc}，讓後續辨識更穩定。"))

    # ── 4) 逐字稿轉錄 ─────────────────────────────────────
    eng = proc.get("transcribe_engine", "mlx-whisper")
    dur = proc.get("audio_duration_text", "")
    segs = proc.get("segment_count")
    line = f"逐字稿轉錄：使用 **{eng}** 產出逐字稿"
    if dur:  line += f"（音訊長度約 {dur}）"
    if segs: line += f"，共切出約 {segs} 個語意片段"
    items.append(_bl(line + "。"))

    # ── 5) 快取策略 ────────────────────────────────────────
    items.append(_bl("快取策略：" + ("本次命中既有轉錄快取，略過重跑逐字稿，整體處理時間較短。"
                        if proc.get("used_cache") else
                        "本次未命中既有轉錄快取，逐字稿為重新轉錄產生。")))

    # ── 6) 摘要生成 + ⚙️ Final 詳細（無論 chunked 與否均顯示）───
    llm     = proc.get("llm_usage") or {}
    chk_u   = llm.get("chunk") or {}
    fin_u   = llm.get("final") or {}

    fin_req = fin_u.get("requested_model") or proc.get("final_model") or "openai-codex/gpt-5.4"
    fin_suc = fin_u.get("final_used_model") or fin_req
    fin_fb   = fin_u.get("used_fallback", False)
    fin_chain = " → ".join(fin_u.get("fallback_chain") or proc.get("final_fallback_chain") or [])

    if proc.get("used_chunking"):
        n     = proc.get("chunk_count", "多")
        chk_req = proc.get("chunk_model") or chk_u.get("requested_model") or "Haiku"
        chk_suc = "、".join(chk_u.get("success_models") or []) or chk_req
        chk_fb   = chk_u.get("used_fallback", False)
        chk_chain = " → ".join(proc.get("chunk_fallback_chain") or [])
        items.append(_bl(
            f"摘要生成：長音檔模式，先分成 {n} 段以 **{chk_req}** 做分段重點整理，再由 **{fin_req}** 整併，"
            f"套用 EMBA 自動子模板（D1 理論 / D2 個案 / D3 行政參訪 / D4 講評+行政混搭）。"))
        items.append(_model_line("Chunk 指定模型：", chk_req, indent=1))
        if chk_suc:
            items.append(_model_line(
                "Chunk 實際成功模型：",
                chk_u.get("success_models", [chk_req])[0] if (chk_u.get("success_models") or []) else chk_req,
                suffix=f"（{'有觸發 fallback' if chk_fb else '未觸發 fallback'}）" if chk_suc else '',
                indent=1,
            ))
        if chk_chain:
            items.append(_model_chain_line("Chunk fallback 鏈：", proc.get("chunk_fallback_chain") or [], indent=1))
    else:
        items.append(_bl(
            f"摘要生成：直接對完整逐字稿生成摘要，使用 **{fin_req}**，"
            f"套用 EMBA 自動子模板（D1 理論 / D2 個案 / D3 行政參訪 / D4 講評+行政混搭）。"))

    # ⚙️ Final（始終顯示）
    items.append(_model_line("Final 指定模型：", fin_req, indent=1))
    items.append(_model_line(
        "Final 實際成功模型：",
        fin_suc,
        suffix=f"（{'有觸發 fallback' if fin_fb else '未觸發 fallback'}）",
        indent=1,
    ))
    if fin_chain:
        items.append(_model_chain_line("Final fallback 鏈：", fin_u.get("fallback_chain") or proc.get("final_fallback_chain") or [], indent=1))

    # ── 7) 說話者處理 ──────────────────────────────────────
    items.append(_bl("說話者處理：" + ("有啟用說話者分辨（speaker diarization）。"
                      if proc.get("used_diarization") else
                      "未啟用說話者分辨 / speaker diarization（以穩定與速度優先）。")))

    ocr_summary = proc.get("ocr_summary") or {}
    if ocr_summary.get("image_count"):
        line = (
            f"OCR 補充：共處理 {ocr_summary.get('image_count', 0)} 張圖片，"
            f"成功 {ocr_summary.get('success_count', 0)} 張，失敗 {ocr_summary.get('failed_count', 0)} 張，"
            f"擷取約 {ocr_summary.get('total_chars', 0)} 字。"
        )
        if ocr_summary.get("warning"):
            line += f" 注意：{ocr_summary.get('warning')}。"
        items.append(_bl(line))
        if metadata.get("detailed_material_restore"):
            items.append(_bl("教材還原模式：已啟用 detailed_material_restore / high_priority_exam_material，教材照片 OCR 會以高保留度方式納入最終摘要。"))

    # ── 8) 耗時 ───────────────────────────────────────────
    te = proc.get("transcribe_elapsed_text", "")
    ts = proc.get("transcribe_elapsed_sec", 0)
    ce = proc.get("chunk_elapsed_text", "")
    se = proc.get("summary_elapsed_text", "")
    total = proc.get("total_elapsed_text", "")
    pts = []
    if te:  pts.append(f"轉錄 {te}")
    if ce:  pts.append(f"分段整理 {ce}")
    if se:  pts.append(f"摘要生成 {se}")
    if pts and total:
        items.append(_bl(f"耗時：{' ＋ '.join(pts)}，總計約 {total}。"))
    elif pts:
        items.append(_bl(f"耗時：{' ＋ '.join(pts)}。"))
    elif total:
        items.append(_bl(f"耗時：總計約 {total}。"))
    elif ts > 0:
        items.append(_bl(f"耗時：轉錄約 {int(ts)} 秒。"))

    # ── 9) 上傳歸檔（含 Notion custom emoji） ─────────────────
    notion_emoji_rt = notion_service_emoji("notion")
    obsidian_emoji_rt = notion_service_emoji("obsidian")
    gray_ann = {"italic": True, "color": "gray"}
    bold_ann = {"bold": True, "italic": True, "color": "gray"}

    upload_rich = []
    upload_rich.append({"type": "text", "text": {"content": "上傳歸檔：同步寫入 "}, "annotations": gray_ann})
    if notion_emoji_rt:
        r = dict(notion_emoji_rt)
        r["annotations"] = dict(r.get("annotations", {}))
        r["annotations"].update(bold_ann)
        upload_rich.append(r)
    upload_rich.append({"type": "text", "text": {"content": "Notion 課堂摘要庫"}, "annotations": bold_ann})
    upload_rich.append({"type": "text", "text": {"content": " ＋ "}, "annotations": gray_ann})
    if obsidian_emoji_rt:
        r = dict(obsidian_emoji_rt)
        r["annotations"] = dict(r.get("annotations", {}))
        r["annotations"].update(bold_ann)
        upload_rich.append(r)
    upload_rich.append({"type": "text", "text": {"content": "Obsidian 本地 Vault"}, "annotations": bold_ann})
    upload_rich.append({"type": "text", "text": {"content": "（EMBA/114-2/每週課堂筆記）。"}, "annotations": gray_ann})
    items.append(_bl_rich(upload_rich))

    _disclaimer_text = (
        "⚠️ 本筆記摘要為 AI Agent :openclaw-dark:調用大語言模型（LLM）"
        "自動化 Workflow 生成。依據使用者提供錄音檔、加上個人筆記及其他補充材料"
        "進行自動交叉校對完成，但仍可能存在誤解、遺漏、錯別字或表述偏差；"
        "若需正式引用、對外使用或作為決策依據，請務必加以核實。"
    )

    heading_rich = []
    oc_emoji = _emoji_with_gray(notion_emoji_mention("openclaw-dark"), bold=False)
    if oc_emoji:
        heading_rich.append(oc_emoji)
    heading_rich.append({
        "type": "text",
        "text": {"content": "作業路徑說明"},
        "annotations": {
            "bold": False,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    })

    return [
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": heading_rich,
                "is_toggleable": True,
                "children": [*items, _quote_disclaimer(_disclaimer_text)],
            },
        },
    ]


# ============================================================
# 商務會談
# ============================================================

def _upload_business(metadata, summary, transcript_text, transcription):
    notion = _get_notion_client()
    db_id = DB_CONFIG["business"]["database_id"]
    schema = validate_notion_schema("business")
    duration = transcription.get("duration_sec", 0)
    meeting = metadata.get("meeting_name", "未命名會談")
    company = metadata.get("target_company", "")
    date = metadata.get("date", "")

    props = {}
    title_field = next((k for k, v in schema.items() if v == "title"), "摘要名稱")
    title_text = f"{company} x {meeting}" if company else meeting
    props[title_field] = _title_prop(f"{title_text} {date}")

    if "日期" in schema and date:
        props["日期"] = {"date": {"start": date}}
    if "類別" in schema and metadata.get("category"):
        props["類別"] = {"select": {"name": metadata["category"]}}
    if "會談地點" in schema and metadata.get("location"):
        props["會談地點"] = _rich_text_prop(metadata["location"])
    if "課別歸屬" in schema and metadata.get("department"):
        props["課別歸屬"] = {"select": {"name": metadata["department"]}}
    if "對象公司" in schema and company:
        props["對象公司"] = _rich_text_prop(company)

    participants = metadata.get("participants", [])
    if "對象人員" in schema and participants:
        props["對象人員"] = _rich_text_prop(", ".join(participants))

    action_items = _extract_action_items(summary)
    if "跟進事項" in schema and action_items:
        props["跟進事項"] = _rich_text_prop(action_items)

    if "狀態" in schema:
        props["狀態"] = {"select": {"name": "待跟進"}}
    if "錄音長度" in schema:
        props["錄音長度"] = _rich_text_prop(_fmt_dur(duration))

    children = []
    if metadata.get('selected_template') not in ('D', 'E'):
        children.extend(_business_report_blocks(metadata))
    summary_body = _strip_workflow_footer_markdown(summary)
    children.extend(_md_to_blocks(summary_body))
    children += _workflow_footer_blocks(metadata)
    return _create_page(notion, db_id, props, children)


def _extract_action_items(summary: str) -> str:
    lines = []
    for line in summary.split("\n"):
        s = line.strip()
        if s.startswith("- [ ]") or s.startswith("- [x]"):
            clean = s.replace("- [ ] ", "").replace("- [x] ", "✅ ")
            lines.append(clean)
    return "\n".join(lines)


# ============================================================
# Business report block (for weekly sales meeting)
# ============================================================

def _business_report_blocks(metadata) -> list:
    """Append a copy-ready Markdown template as a Notion code block.

    Only the summary lines inside the code block should be numbered list:
      1. ...
      2. ...
    The full page content below the code block is rendered from the main summary template (A/B/C).
    """
    title = '## 業務會報版：'
    meeting = metadata.get('meeting_name') or metadata.get('course_name') or ''
    date = metadata.get('date', '')
    location = metadata.get('location', '')
    people = ''
    if metadata.get('participants'):
        people = ', '.join(metadata.get('participants') or [])
    elif metadata.get('attendees'):
        people = ', '.join(metadata.get('attendees') or [])

    report_lines = metadata.get('report_lines') or []

    # Ensure we only keep numbered bullet lines; do NOT inject placeholders.
    numbered = []
    for ln in report_lines:
        s = (ln or '').strip()
        if re.match(r'^\d+\.', s):
            numbered.append(s)

    if not numbered:
        numbered = ['1. （此處將自動填入摘要重點；若為空表示摘要模板未產出「業務會報版摘要」段落）']

    md = "\n".join([
        title,
        f"- 主題：{meeting}",
        f"- 日期：{date}",
        f"- 地點：{location}",
        f"- 人員：{people}",
        '- 摘要：',
        *('  ' + s for s in numbered),
    ])

    return [
        {"object": "block", "type": "divider", "divider": {}},
        _heading_block(2, '業務會報版（可一鍵複製）'),
        {
            "object": "block",
            "type": "code",
            "code": {
                "language": "markdown",
                "rich_text": [{"type": "text", "text": {"content": md[:2000]}}],
            },
        },
    ]


# ============================================================
# Notion Blocks
# ============================================================

def _validate_page_parent(page: dict, expected_db_id: str, expected_ds_id: Optional[str] = None):
    parent = (page or {}).get("parent") or {}
    if not _parent_matches_expected(parent, expected_db_id, expected_ds_id):
        raise RuntimeError(
            "Notion parent mismatch: "
            f"expected database_id={expected_db_id} data_source_id={expected_ds_id or '-'}; "
            f"got parent={parent}"
        )


def _create_page(notion, db_id, properties, children) -> str:
    parent_payload, _db, ds_id = _resolve_parent_target(notion, db_id)
    page = notion.pages.create(
        parent=parent_payload,
        properties=properties,
        children=children[:100],
    )
    _validate_page_parent(page, db_id, ds_id)
    page_id = page.get("id", "")
    for i in range(100, len(children), 100):
        notion.blocks.children.append(block_id=page_id, children=children[i:i+100])
    url = page.get("url", "")
    logger.info(f"Notion page: {url}")
    return url


def _title_prop(text):
    return {"title": [{"text": {"content": text[:2000]}}]}

def _rich_text_prop(text):
    segs = [{"text": {"content": text[i:i+2000]}} for i in range(0, max(len(text), 1), 2000)]
    return {"rich_text": segs}


def _transcript_toggle_blocks(transcript_text: str) -> list:
    """Put the full transcript under toggle headings (no spill into page body).

    Notion toggle blocks can only include up to ~100 child blocks per request.
    We split long transcripts into multiple toggle headings, each containing
    <= 100 paragraph children.
    """
    # If no transcript, do not add placeholder blocks
    if not (transcript_text or "").strip():
        return []

    blocks = [{"object": "block", "type": "divider", "divider": {}}]

    lines = [ln.strip() for ln in transcript_text.split("\n") if ln.strip()]
    if not lines:
        blocks.append(_paragraph_block("(逐字稿為空)"))
        return blocks

    children = [_paragraph_block(ln) for ln in lines]

    chunk_size = 100
    chunks = [children[i:i+chunk_size] for i in range(0, len(children), chunk_size)]

    for idx, ch in enumerate(chunks, start=1):
        title = "📜 逐字稿原稿" if idx == 1 else f"📜 逐字稿原稿（續{idx-1}）"
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": title}}],
                "is_toggleable": True,
                "children": ch,
            },
        })

    return blocks





def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and "|" in s[1:]


def _is_md_table_separator(line: str) -> bool:
    """Detect the separator row like: | --- | :---: | ---: |"""
    s = line.strip().strip("|")
    parts = [p.strip() for p in s.split("|")]
    if not parts:
        return False
    for p in parts:
        if not p:
            return False
        # allow :, -, spaces
        if not re.fullmatch(r":?-{3,}:?", p.replace(" ", "")):
            return False
    return True


def _split_md_table_row(line: str) -> list:
    # remove outer pipes then split
    s = line.strip().strip("|")
    return [c.strip() for c in s.split("|")]


def _table_block(rows: list, has_header: bool = True) -> dict:
    """Create a real Notion table block.

    rows: list[list[str]]
    """
    width = max((len(r) for r in rows), default=1)
    norm = [r + [""] * (width - len(r)) for r in rows]

    children = []
    for r in norm:
        cells = []
        for cell in r:
            cells.append(_rich_segs(cell) if cell else [])
        children.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": cells},
        })

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": bool(has_header),
            "has_row_header": False,
            "children": children,
        },
    }


# 章節→底色對照表（依標題關鍵字自動套用）
_SECTION_COLOR_MAP = [
    # (關鍵字 tuple, block_color)
    (("老師重點金句", "重點金句", "金句"),          "yellow_background"),
    (("核心觀點",),                                  "orange_background"),
    (("行動項目", "結論 & 行動", "待辦"),            "blue_background"),
    (("待確認", "風險", "風險事項"),                 "red_background"),
    (("主導者指示", "主管指示", "主管重點"),         "purple_background"),
    (("老師講解各環節", "課堂內容詳細還原", "課堂流程還原"), "default"),  # 正文不加底色
    (("作業路徑說明", "使用提醒"),                   "gray"),     # footer 灰色斜體
]

def _section_color_for_heading(heading_text: str) -> str:
    """Return the block color for bullets that follow this heading."""
    for keys, color in _SECTION_COLOR_MAP:
        for k in keys:
            if k in heading_text:
                return color
    return "default"


def _md_to_blocks(md: str) -> list:
    """Convert markdown-ish text to Notion blocks.

    Supports headings, lists, quotes, dividers, todo, and **Markdown pipe tables**.
    Also supports 1-level nested bullets via 2-space indent: `  - item`.

    Pipe tables are converted into real Notion `table` blocks so columns align.

    Extended inline markers (all handled in _rich_segs):
      ==text==  → yellow_background (螢光筆)
      __text__  → underline
      !!text!!  → red bold (警示)
      ~~text~~  → strikethrough

    Auto block color rules (by section heading keyword):
      老師重點金句  → yellow_background
      核心觀點      → orange_background
      行動項目      → blue_background
      待確認/風險   → red_background
      主管指示      → purple_background
    """
    blocks = []
    lines = md.split("\n")
    i = 0

    last_list_block = None      # for nested indent
    current_section_color = "default"   # auto-color from heading context

    while i < len(lines):
        raw = lines[i]
        s = raw.rstrip("\n")
        if not s.strip():
            i += 1
            continue

        # ---- Markdown pipe table ----
        if _is_md_table_row(s.strip()) and i + 1 < len(lines) and _is_md_table_separator(lines[i + 1]):
            header = _split_md_table_row(lines[i])
            i += 2  # skip header + separator
            body = []
            while i < len(lines) and _is_md_table_row(lines[i].strip()):
                body.append(_split_md_table_row(lines[i]))
                i += 1
            table_rows = [header] + body

            max_rows = 80
            if len(table_rows) <= max_rows:
                blocks.append(_table_block(table_rows, has_header=True))
            else:
                blocks.append(_heading_block(3, "表格（分段）"))
                for k in range(0, len(table_rows), max_rows):
                    chunk = table_rows[k:k+max_rows]
                    if chunk and chunk[0] != header:
                        chunk = [header] + chunk
                    blocks.append(_table_block(chunk, has_header=True))
            last_list_block = None
            continue

        st = s.strip()

        # ---- nested list (2-space indent) ----
        if s.startswith("  - ") and last_list_block is not None:
            if st.startswith("- [ ] "):
                child = _todo_block(st[6:], False)
            elif st.startswith("- [x] "):
                child = _todo_block(st[6:], True)
            else:
                child = _bullet_block(st[2:])
            parent_type = last_list_block.get('type')
            if parent_type == 'bulleted_list_item':
                last_list_block['bulleted_list_item'].setdefault('children', []).append(child)
            elif parent_type == 'to_do':
                last_list_block['to_do'].setdefault('children', []).append(child)
            else:
                blocks.append(child)
            i += 1
            continue

        # ---- normal markdown-ish lines ----
        if st.startswith("###### "):
            heading_text = st[7:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(3, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st.startswith("##### "):
            heading_text = st[6:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(3, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st.startswith("#### "):
            heading_text = st[5:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(3, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st.startswith("### "):
            heading_text = st[4:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(3, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st.startswith("## "):
            heading_text = st[3:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(2, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st.startswith("# "):
            heading_text = st[2:]
            hcolor = _section_color_for_heading(heading_text)
            blocks.append(_heading_block(1, heading_text, color=hcolor))
            current_section_color = hcolor
            last_list_block = None
        elif st == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            current_section_color = "default"
            last_list_block = None
        elif st.startswith("- [ ] "):
            b = _todo_block(st[6:], False, color=current_section_color)
            blocks.append(b)
            last_list_block = b
        elif st.startswith("- [x] "):
            b = _todo_block(st[6:], True, color=current_section_color)
            blocks.append(b)
            last_list_block = b
        elif st.startswith("- "):
            b = _bullet_block(st[2:], color=current_section_color)
            blocks.append(b)
            last_list_block = b
        elif st.startswith("> "):
            blocks.append(_quote_block(st[2:], color=current_section_color))
            last_list_block = None
        else:
            blocks.append(_paragraph_block(st))
            last_list_block = None
        i += 1

    # ---- Post-process: wrap designated sections into toggle headings ----
    blocks = _wrap_toggle_sections(blocks)

    return blocks


# Heading keywords that should become toggleable (collapsed by default) in Notion
_TOGGLE_SECTION_KEYWORDS = ("課堂流程還原", "作業路徑說明")


def _wrap_toggle_sections(blocks: list) -> list:
    """Find headings matching _TOGGLE_SECTION_KEYWORDS and collapse their
    children into a Notion toggleable heading block.

    Children = all blocks after the heading until the next heading of
    same or higher level (or end of list).
    Notion API limit: max 100 children per toggle block.
    """
    result = []
    i = 0
    while i < len(blocks):
        blk = blocks[i]
        # Check if this is a heading that should be toggleable
        heading_type = None
        heading_text = ""
        for lvl in (1, 2, 3):
            ht = f"heading_{lvl}"
            if blk.get("type") == ht:
                heading_type = ht
                rt = blk.get(ht, {}).get("rich_text", [])
                heading_text = "".join(seg.get("text", {}).get("content", "") for seg in rt)
                break

        if heading_type and any(kw in heading_text for kw in _TOGGLE_SECTION_KEYWORDS):
            # Determine heading level number for comparison
            toggle_level = int(heading_type.split("_")[1])
            # Collect children
            children = []
            j = i + 1
            while j < len(blocks):
                child_blk = blocks[j]
                # Check if next block is a heading of same or higher level
                is_boundary = False
                for lvl in range(1, toggle_level + 1):
                    if child_blk.get("type") == f"heading_{lvl}":
                        is_boundary = True
                        break
                if is_boundary:
                    break
                children.append(child_blk)
                j += 1

            # Build toggle heading (chunk children at 100 per Notion API limit)
            chunk_size = 100
            if len(children) <= chunk_size:
                toggle_blk = {
                    "object": "block",
                    "type": heading_type,
                    heading_type: {
                        "rich_text": blk[heading_type]["rich_text"],
                        "is_toggleable": True,
                        "children": children if children else [_paragraph_block("（本次無課堂流程還原內容）")],
                    },
                }
                if blk[heading_type].get("color", "default") != "default":
                    toggle_blk[heading_type]["color"] = blk[heading_type]["color"]
                result.append(toggle_blk)
            else:
                # Multiple toggle blocks for very long sections
                for ci, start in enumerate(range(0, len(children), chunk_size)):
                    chunk = children[start:start + chunk_size]
                    suffix = f"（續{ci}）" if ci > 0 else ""
                    rt_copy = [dict(seg) for seg in blk[heading_type]["rich_text"]]
                    if suffix and rt_copy:
                        last_seg = dict(rt_copy[-1])
                        last_seg["text"] = dict(last_seg.get("text", {}))
                        last_seg["text"]["content"] = last_seg["text"].get("content", "") + suffix
                        rt_copy[-1] = last_seg
                    toggle_blk = {
                        "object": "block",
                        "type": heading_type,
                        heading_type: {
                            "rich_text": rt_copy,
                            "is_toggleable": True,
                            "children": chunk,
                        },
                    }
                    result.append(toggle_blk)
            i = j  # skip past collected children
        else:
            result.append(blk)
            i += 1

    return result


def _heading_block(level, text, color: str = "default"):
    t = f"heading_{level}"
    b = {"object": "block", "type": t, t: {"rich_text": _rich_segs(text)}}
    if color != "default":
        b[t]["color"] = color
    return b

def _paragraph_block(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_segs(text)}}

def _bullet_block(text, color: str = "default"):
    b = {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_segs(text)}}
    if color != "default":
        b["bulleted_list_item"]["color"] = color
    return b

def _todo_block(text, checked=False, color: str = "default"):
    b = {"object": "block", "type": "to_do", "to_do": {"rich_text": _rich_segs(text), "checked": checked}}
    if color != "default":
        b["to_do"]["color"] = color
    return b

def _quote_block(text, color: str = "default"):
    b = {"object": "block", "type": "quote", "quote": {"rich_text": _rich_segs(text)}}
    if color != "default":
        b["quote"]["color"] = color
    return b

def _rich_segs(text: str) -> list:
    """Parse inline markdown + extended markers into Notion rich_text segments.

    Supported markers:
      **text**  → bold
      *text*    → italic
      `text`    → code
      ==text==  → yellow_background (螢光筆)
      __text__  → underline (底線)
      !!text!!  → red text (警示)
      ~~text~~  → strikethrough (刪除線)
    """
    segs = []
    pattern = re.compile(
        r'\*\*(.+?)\*\*'      # bold
        r'|\*(.+?)\*'         # italic
        r'|`(.+?)`'           # code
        r'|==(.+?)=='         # highlight (yellow_background)
        r'|__(.+?)__'         # underline
        r'|!!(.+?)!!'         # alert (red)
        r'|~~(.+?)~~',        # strikethrough
        re.DOTALL
    )
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            chunk = text[last:m.start()]
            for j in range(0, max(len(chunk), 1), 2000):
                segs.append({"type": "text", "text": {"content": chunk[j:j+2000]}})
        if m.group(1) is not None:   # **bold**
            segs.append({"type": "text", "text": {"content": m.group(1)[:2000]}, "annotations": {"bold": True}})
        elif m.group(2) is not None: # *italic*
            segs.append({"type": "text", "text": {"content": m.group(2)[:2000]}, "annotations": {"italic": True}})
        elif m.group(3) is not None: # `code`
            segs.append({"type": "text", "text": {"content": m.group(3)[:2000]}, "annotations": {"code": True}})
        elif m.group(4) is not None: # ==highlight==
            segs.append({"type": "text", "text": {"content": m.group(4)[:2000]}, "annotations": {"color": "yellow_background"}})
        elif m.group(5) is not None: # __underline__
            segs.append({"type": "text", "text": {"content": m.group(5)[:2000]}, "annotations": {"underline": True}})
        elif m.group(6) is not None: # !!alert!!
            segs.append({"type": "text", "text": {"content": m.group(6)[:2000]}, "annotations": {"color": "red", "bold": True}})
        elif m.group(7) is not None: # ~~strikethrough~~
            segs.append({"type": "text", "text": {"content": m.group(7)[:2000]}, "annotations": {"strikethrough": True}})
        last = m.end()
    if last < len(text):
        chunk = text[last:]
        for j in range(0, max(len(chunk), 1), 2000):
            segs.append({"type": "text", "text": {"content": chunk[j:j+2000]}})
    if not segs:
        segs.append({"type": "text", "text": {"content": ""}})
    return segs


# ============================================================
# Public wrappers (backward compat)
# ============================================================

def upload_emba(metadata, summary, transcript_text, duration_sec):
    """Wrapper for lecture_pipeline compatibility."""
    tx = duration_sec if isinstance(duration_sec, dict) else {"duration_sec": duration_sec}
    return _upload_emba(metadata, summary, transcript_text, tx)


def upload_business(metadata, summary, transcript_text, duration_sec):
    """Wrapper for lecture_pipeline compatibility."""
    tx = duration_sec if isinstance(duration_sec, dict) else {"duration_sec": duration_sec}
    return _upload_business(metadata, summary, transcript_text, tx)


def overwrite_page(page_id: str, summary: str, metadata: dict, expected_db_type: Optional[str] = None) -> int:
    """覆蓋現有 Notion 頁面的所有 blocks（刪除舊的，寫入新的摘要 + footer）。

    ⚠️ 這是唯一正確的手動覆蓋方式。不要自己寫 md_to_blocks。
    ⚠️ 若頁面不在已知 DB（emba/business），直接拒絕，避免誤蓋使用者原始筆記。
    ⚠️ expected_db_type=None 時，仍會驗證目標頁面確實屬於已知 DB 之一。

    Args:
        page_id: Notion page ID（32 位元不帶 dash，或帶 dash 均可）
        summary: 由 LLM 生成的 markdown 摘要文字
        metadata: 含 course_name, professor, date 等欄位的 dict
        expected_db_type: 'emba' / 'business'；若提供則必須與頁面 parent 完全符合；
                          若為 None 則仍需確認頁面在已知 DB 之一，否則拒絕。

    Returns:
        寫入的 block 數量
    """
    notion = _get_notion_client()

    # ── 硬護欄：確保目標頁面在已知 DB 之一 ──────────────────────────
    # 無論 expected_db_type 是否提供，都要驗證。
    # 這防止任何人（包括 sub-agent / 錯誤指令）誤覆蓋使用者自己的筆記頁。
    page_meta = notion.pages.retrieve(page_id)
    actual_parent = (page_meta or {}).get("parent") or {}
    actual_db_id = (actual_parent.get("database_id") or "").replace("-", "")
    actual_ds_id = (actual_parent.get("data_source_id") or "").replace("-", "")

    known_db_ids = {v["database_id"].replace("-", "") for v in DB_CONFIG.values()}

    page_in_known_db = (
        actual_db_id in known_db_ids
        or actual_ds_id in known_db_ids
    )

    if not page_in_known_db:
        raise RuntimeError(
            f"overwrite_page 拒絕執行：目標頁面 {page_id} 不在任何已知 DB "
            f"(parent={actual_parent})。\n"
            "只能 overwrite 課堂摘要庫 或 商務會談摘要DB 的頁面。\n"
            "若要新增到 DB，請使用 upload_emba() 或 upload_business()。"
        )

    if expected_db_type:
        db_id = DB_CONFIG[expected_db_type]["database_id"]
        _parent_payload, _db, ds_id = _resolve_parent_target(notion, db_id)
        _validate_page_parent(page_meta, db_id, ds_id)

    # 刪除所有現有 blocks
    has_more, cursor, deleted = True, None, 0
    while has_more:
        kwargs = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        res = notion.blocks.children.list(**kwargs)
        for b in res.get("results", []):
            if not b.get("archived", False):
                try:
                    notion.blocks.delete(b["id"])
                    deleted += 1
                except Exception:
                    pass
        has_more = res.get("has_more", False)
        cursor = res.get("next_cursor")

    # 組合新 blocks（Obsidian 連結只保留在 Obsidian vault 版，不寫入 Notion）
    summary_body = _strip_workflow_footer_markdown(summary)
    all_blocks = _md_to_blocks(summary_body)
    all_blocks += _workflow_footer_blocks(metadata)

    # 寫入（每批 100）
    total = 0
    for i in range(0, len(all_blocks), 100):
        notion.blocks.children.append(page_id, children=all_blocks[i:i+100])
        total += len(all_blocks[i:i+100])

    logger.info(f"overwrite_page: deleted={deleted}, written={total}")
    return total
