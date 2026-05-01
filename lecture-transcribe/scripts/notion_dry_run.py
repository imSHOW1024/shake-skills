#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from notion_upload import preview_notion_write  # noqa: E402


def _extract_page_id(value: str) -> str:
    if not value:
        return ""
    s = value.strip()
    m = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', s)
    if m:
        return m.group(1)
    slug = s.split('?')[0].split('#')[0].rstrip('/').rsplit('/', 1)[-1]
    for part in reversed(slug.split('-')):
        if re.fullmatch(r'[0-9a-fA-F]{32}', part):
            return f"{part[:8]}-{part[8:12]}-{part[12:16]}-{part[16:20]}-{part[20:]}"
    return s


def _stringify(value):
    if value is None:
        return ''
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _load_metadata(markdown_path: Path) -> dict:
    text = markdown_path.read_text(encoding='utf-8')
    data = {}
    if text.startswith('---\n'):
        parts = text.split('\n---\n', 1)
        if len(parts) == 2:
            try:
                data = yaml.safe_load(parts[0][4:]) or {}
            except Exception:
                data = {}
    metadata = {
        'date': _stringify(data.get('date') or ''),
        'type': _stringify(data.get('type') or 'emba'),
        'professor': _stringify(data.get('professor') or ''),
    }
    title = _stringify(data.get('course') or data.get('title') or '')
    if metadata['type'] == 'business':
        metadata['meeting_name'] = title
    else:
        metadata['course_name'] = title
    return metadata


def main() -> int:
    ap = argparse.ArgumentParser(description='Read-only Notion write preview for lecture-transcribe.')
    ap.add_argument('--db-type', choices=['emba', 'business'], default='emba')
    ap.add_argument('--markdown', type=Path, help='Markdown file to infer metadata from frontmatter')
    ap.add_argument('--metadata-json', help='Raw metadata JSON string (overrides frontmatter fields when provided)')
    ap.add_argument('--page', help='Existing Notion page URL or page id to verify before overwrite')
    args = ap.parse_args()

    metadata = {}
    if args.markdown:
        metadata.update(_load_metadata(args.markdown))
    if args.metadata_json:
        metadata.update(json.loads(args.metadata_json))

    page_id = _extract_page_id(args.page) if args.page else None
    preview = preview_notion_write(db_type=args.db_type, metadata=metadata, page_id=page_id)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
