#!/usr/bin/env python3
"""
sync_emba_tasks.py
從 Notion EMBA 課程作業 DB 同步到 Obsidian EMBA 資料夾

用法:
  python3 sync_emba_tasks.py [--dry-run]
"""

import json, os
from datetime import datetime

NOTION_KEY = open("/Users/openclaw/.openclaw/.env").read().split('NOTION_API_KEY=')[1].split()[0]
DS_ID = "33235267-e085-8036-a70c-000b93fb0b7d"
OBSIDIAN_EMBA = "/Users/openclaw/.openclaw/workspace/Obsidian/小龍女知識庫/10 EMBA"

COURSE_FILE_MAP = {
    "跨文化交流與研習": "114-2 跨文化交流與研習.md",
    "企業危機管理":     "114-2 企業危機管理.md",
    "企業研究方法":     "114-2 企業研究方法.md",
    "全球台商個案研究": "114-2 全球台商個案研討.md",
    "消費者行為":       "114-2 消費者行為.md",
    "科技與人文講座":   "114-2 科技與人文.md",
}

STATUS_ICON = {
    "完成": "done",
    "進行中": "doing",
    "未開始": "todo",
}

def fetch_tasks():
    import urllib.request
    url = f"https://api.notion.com/v1/data_sources/{DS_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json"
    }
    payload = {"page_size": 100}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        return result.get('results', [])

def parse_task(page):
    props = page.get('properties', {})
    title = ''.join([t.get('plain_text', '') for t in props.get('作業 名稱', {}).get('title', [])])
    course = props.get('課程', {}).get('select', {}).get('name', None)
    task_types = [t.get('name') for t in props.get('作業類型', {}).get('multi_select', [])]
    due_raw = props.get('期限', {}).get('date', {})
    due_str = due_raw.get('start', None) if due_raw else None
    status = props.get('狀態', {}).get('status', {}).get('name', '未開始')
    desc = ''.join([t.get('plain_text', '') for t in props.get('作業 / 報告 方式說明', {}).get('rich_text', [])])
    notion_id = page.get('id', '').replace('-', '')
    return {
        "title":  title,
        "course": course,
        "types":  task_types,
        "due":    due_str[:10] if due_str else None,
        "status": status,
        "desc":   desc,
        "url":    f"https://www.notion.so/{notion_id}",
    }

def render_course(tasks, course_name, dry_run=False):
    filtered = [t for t in tasks if t['course'] == course_name]
    # Sort: done last, then by due date
    filtered.sort(key=lambda t: (
        t['status'] == '完成',
        t['due'] or '9999',
    ))

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [
        "---",
        f"last_sync: {now}",
        f"notion_db: https://www.notion.so/EMBA-DB-33235267e0858019ac5ddffd8962b382",
        "sync_command: /sync-emba-tasks",
        "---",
        "",
        f"# {course_name} | 功課與報告",
        "",
        f"共 {len(filtered)} 項（由 Notion EMBA 課程作業 DB 同步）",
        "",
    ]

    if not filtered:
        lines.append("_目前尚無記錄的任務_")
    else:
        for t in filtered:
            icon = STATUS_ICON.get(t['status'], 'todo')
            types_str = '、'.join(t['types']) if t['types'] else '一般'
            due_display = f" | 期限：{t['due']}" if t['due'] else ""
            desc_short = t['desc'][:120] + ('...' if len(t['desc']) > 120 else '') if t['desc'] else ''
            notion_id_short = t['url'].replace('https://www.notion.so/', '')

            lines.append(f"- [{icon}] **{t['title']}**")
            lines.append(f"  - 類型：{types_str} {due_display}")
            lines.append(f"  - 狀態：{t['status']}")
            if desc_short:
                lines.append(f"  - 說明：{desc_short}")
            lines.append(f"  - Notion：{t['url']}")
            lines.append("")

    content = '\n'.join(lines)
    fname = COURSE_FILE_MAP.get(course_name)
    if not fname:
        print(f"  WARNING: 無法對應檔名：{course_name}")
        return

    fpath = os.path.join(OBSIDIAN_EMBA, fname)
    if dry_run:
        print(f"\n[DRY RUN] {fname}")
        print(content[:600])
        return

    os.makedirs(OBSIDIAN_EMBA, exist_ok=True)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  OK {fname} ({len(filtered)} items)")

def main(dry_run=False):
    print("Syncing Notion EMBA DB -> Obsidian...")
    tasks = [parse_task(p) for p in fetch_tasks()]
    print(f"  Fetched {len(tasks)} records from Notion")

    for course_name in COURSE_FILE_MAP:
        render_course(tasks, course_name, dry_run=dry_run)

    if not dry_run:
        print(f"\nDone! Obsidian path: {OBSIDIAN_EMBA}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
