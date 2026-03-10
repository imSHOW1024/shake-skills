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


def _retrieve_schema(notion, db_id: str) -> dict:
    """Return property schema for a Notion database.

    Supports both legacy API (database.properties) and newer API where
    databases include `data_sources` and properties live on the data source.
    """
    db = notion.databases.retrieve(db_id)

    # Legacy
    if isinstance(db, dict) and "properties" in db:
        return {name: prop.get("type") for name, prop in db["properties"].items()}

    # New API (databases -> data_sources)
    data_sources = (db or {}).get("data_sources") or []
    if data_sources:
        ds_id = data_sources[0].get("id")
        if ds_id:
            ds = notion.data_sources.retrieve(ds_id)
            if isinstance(ds, dict) and "properties" in ds:
                return {name: prop.get("type") for name, prop in ds["properties"].items()}

    raise KeyError(f"Unable to read schema for database_id={db_id}. Keys={list((db or {}).keys())}")


def validate_notion_schema(db_type: str = "emba") -> dict:
    notion = _get_notion_client()
    db_id = DB_CONFIG[db_type]["database_id"]
    schema = _retrieve_schema(notion, db_id)
    logger.info(f"Notion [{db_type}] schema: {schema}")
    return schema


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


# ============================================================
# EMBA
# ============================================================

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
    if "關鍵字" in schema and metadata.get("keywords"):
        props["關鍵字"] = {"multi_select": [{"name": kw} for kw in metadata["keywords"]]}
    if "學期" in schema:
        props["學期"] = {"select": {"name": "114-2"}}

    children = _md_to_blocks(summary)
    children.extend(_transcript_toggle_blocks(transcript_text))
    return _create_page(notion, db_id, props, children)


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

    children = _md_to_blocks(summary)
    children.extend(_transcript_toggle_blocks(transcript_text))
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
# Notion Blocks
# ============================================================

def _create_page(notion, db_id, properties, children) -> str:
    page = notion.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=children[:100],
    )
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

def _md_to_blocks(md: str) -> list:
    """Convert markdown-ish text to Notion blocks.

    Supports headings, lists, quotes, dividers, todo, and **Markdown pipe tables**.
    Pipe tables are converted into real Notion `table` blocks so columns align.
    """
    blocks = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        # ---- Markdown pipe table ----
        if _is_md_table_row(s) and i + 1 < len(lines) and _is_md_table_separator(lines[i + 1]):
            header = _split_md_table_row(lines[i])
            i += 2  # skip header + separator
            body = []
            while i < len(lines) and _is_md_table_row(lines[i].strip()):
                body.append(_split_md_table_row(lines[i]))
                i += 1
            table_rows = [header] + body

            # Notion has practical limits; keep it safe.
            # If a table is huge, split into multiple tables.
            max_rows = 80
            if len(table_rows) <= max_rows:
                blocks.append(_table_block(table_rows, has_header=True))
            else:
                blocks.append(_heading_block(3, "表格（分段）"))
                for k in range(0, len(table_rows), max_rows):
                    chunk = table_rows[k:k+max_rows]
                    # ensure each chunk has a header
                    if chunk and chunk[0] != header:
                        chunk = [header] + chunk
                    blocks.append(_table_block(chunk, has_header=True))
            continue

        # ---- normal markdown-ish lines ----
        if s.startswith("### "):
            blocks.append(_heading_block(3, s[4:]))
        elif s.startswith("## "):
            blocks.append(_heading_block(2, s[3:]))
        elif s.startswith("# "):
            blocks.append(_heading_block(1, s[2:]))
        elif s == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif s.startswith("- [ ] "):
            blocks.append(_todo_block(s[6:], False))
        elif s.startswith("- [x] "):
            blocks.append(_todo_block(s[6:], True))
        elif s.startswith("- "):
            blocks.append(_bullet_block(s[2:]))
        elif s.startswith("> "):
            blocks.append(_quote_block(s[2:]))
        else:
            blocks.append(_paragraph_block(s))
        i += 1

    return blocks


def _heading_block(level, text):
    t = f"heading_{level}"
    return {"object": "block", "type": t, t: {"rich_text": _rich_segs(text)}}

def _paragraph_block(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_segs(text)}}

def _bullet_block(text):
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_segs(text)}}

def _todo_block(text, checked=False):
    return {"object": "block", "type": "to_do", "to_do": {"rich_text": _rich_segs(text), "checked": checked}}

def _quote_block(text):
    return {"object": "block", "type": "quote", "quote": {"rich_text": _rich_segs(text)}}

def _rich_segs(text):
    return [{"type": "text", "text": {"content": text[i:i+2000]}} for i in range(0, max(len(text), 1), 2000)]


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
