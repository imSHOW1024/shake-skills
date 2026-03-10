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


def validate_notion_schema(db_type: str = "emba") -> dict:
    notion = _get_notion_client()
    db_id = DB_CONFIG[db_type]["database_id"]
    db = notion.databases.retrieve(db_id)
    schema = {name: prop["type"] for name, prop in db["properties"].items()}
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
            props[field] = _rich_text_prop(val)
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
    blocks = [{"object": "block", "type": "divider", "divider": {}}]

    toggle_children = []
    for line in transcript_text.split("\n"):
        s = line.strip()
        if s:
            toggle_children.append(_paragraph_block(s))

    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "📜 逐字稿原稿"}}],
            "is_toggleable": True,
            "children": toggle_children[:100],
        },
    })

    if len(toggle_children) > 100:
        blocks.append(_paragraph_block("⬆️ 逐字稿續..."))
        blocks.extend(toggle_children[100:])

    return blocks


def _md_to_blocks(md: str) -> list:
    blocks = []
    for line in md.split("\n"):
        s = line.strip()
        if not s:
            continue
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
