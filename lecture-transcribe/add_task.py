#!/usr/bin/env python3
"""
EMBA 課程任務寫入 Notion 小工具
由 lecture-transcribe 流程呼叫，或手動執行

用法:
  python3 add_task.py --name "個案分析報告" --course "全球台商個案研究" \\
      --type "期中報告" --due "2026-04-15" --desc "分組報告"

  python3 add_task.py --interactive   # 互動模式
  python3 add_task.py --auto "摘要文字..."  # 自動偵測
"""

import json, sys, os

NOTION_KEY = os.environ.get("NOTION_API_KEY",
    open("/Users/openclaw/.openclaw/.env").read().split('NOTION_API_KEY=')[1].split()[0])

# EMBA 課程作業 DB
DB_ID = "33235267e0858097a88ed8b67de9b3cd"
DS_ID = "33235267-e085-8036-a70c-000b93fb0b7d"

COURSE_MAP = {
    "跨文化交流": "跨文化交流與研習",
    "企業危機": "企業危機管理",
    "研究方法": "企業研究方法",
    "台商個案": "全球台商個案研究",
    "消費者行為": "消費者行為",
    "科技與人文": "科技與人文講座",
}

def get_course(text):
    for keyword, course in COURSE_MAP.items():
        if keyword in text:
            return course
    return None

def add_task(name, course=None, task_type="課堂作業", due=None, desc=None, source_id=None, status="未開始"):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json"
    }

    # Auto-detect course from name if not provided
    if not course and name:
        course = get_course(name)

    payload = {
        "parent": {"database_id": DB_ID},
        "properties": {
            "作業 名稱": {"title": [{"text": {"content": name}}]},
            "狀態": {"status": {"name": status}},
        }
    }

    if course:
        payload["properties"]["課程"] = {"select": {"name": course}}

    if task_type:
        payload["properties"]["作業類型"] = {"multi_select": [{"name": task_type}]}

    if due:
        payload["properties"]["期限"] = {"date": {"start": due}}

    if desc:
        payload["properties"]["作業 / 報告 方式說明"] = {"rich_text": [{"text": {"content": desc}}]}

    if source_id:
        payload["properties"]["課堂摘要DB"] = {"relation": [{"id": source_id}]}

    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        if result.get('object') == 'page':
            print(f"✅ 已新增：{name}")
            return result['id']
        else:
            print(f"❌ 失敗：{result.get('message', result)}")
            return None

def detect_and_add_from_summary(summary_text, source_id=None):
    """從摘要文字自動偵測任務並寫入 Notion"""
    import re
    tasks_found = []

    task_patterns = [
        (r'期中報告[:：]?\s*([^\n，,。]+)', '期中報告'),
        (r'期末報告[:：]?\s*([^\n，,。]+)', '期末報告'),
        (r'簡報[:：]?\s*([^\n，,。]+)', '小組發表'),
        (r'上台報告[:：]?\s*([^\n，,。]+)', '小組發表'),
        (r'作業[:：]?\s*([^\n，,。]+)', '課堂作業'),
        (r'繳交期限?[:：]\s*(\d+[/\-月日]\d+)', '課堂作業'),
        (r'截止[:：]\s*(\d+[/\-月日]\d+)', '課堂作業'),
    ]

    due_pattern = r'(\d{4}[/\-月日]\d+)'

    course = get_course(summary_text)

    lines = summary_text.split('\n')
    for line in lines:
        for pattern, task_type in task_patterns:
            match = re.search(pattern, line)
            if match:
                task_name = match.group(1).strip() if match.lastindex else line.strip()
                due_match = re.search(due_pattern, line)
                due = None
                if due_match:
                    due_str = due_match.group(1).replace('月', '/').replace('日', '')
                    if '/' in due_str:
                        parts = re.split(r'[/\-]', due_str)
                        if len(parts[0]) <= 2:
                            due = f"2026/{due_str}"
                        else:
                            due = due_str
                tid = add_task(
                    name=task_name[:100],
                    course=course,
                    task_type=task_type,
                    due=due,
                    source_id=source_id
                )
                if tid:
                    tasks_found.append((task_name, task_type))
                break

    return tasks_found

def query_tasks(filters=None):
    """查詢現有任務"""
    import urllib.request
    url = f"https://api.notion.com/v1/data_sources/{DS_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": "2025-09-03",
        "Content-Type": "application/json"
    }
    payload = {"page_size": 50}
    if filters:
        payload["filter"] = filters

    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        return result.get('results', [])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='EMBA 任務寫入 Notion')
    parser.add_argument('--name', help='任務名稱')
    parser.add_argument('--course', help='課程名')
    parser.add_argument('--type', default='課堂作業', help='作業類型')
    parser.add_argument('--due', help='期限 YYYY-MM-DD')
    parser.add_argument('--desc', help='說明')
    parser.add_argument('--source', help='來源摘要ID')
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--auto', help='從摘要文字自動偵測')
    parser.add_argument('--list', action='store_true', help='列出所有任務')
    args = parser.parse_args()

    if args.list:
        tasks = query_tasks()
        print(f"\n📋 EMBA 課程任務（共 {len(tasks)} 筆）\n")
        for r in tasks:
            props = r.get('properties', {})
            title = ''.join([t.get('plain_text', '') for t in props.get('作業 名稱', {}).get('title', [])])
            course = props.get('課程', {}).get('select', {}).get('name', '-')
            task_types = [t.get('name') for t in props.get('作業類型', {}).get('multi_select', [])]
            due = props.get('期限', {}).get('date', {})
            due_str = due.get('start', '無期限')[:10] if due else '無期限'
            status = props.get('狀態', {}).get('status', {}).get('name', '-')
            print(f"  【{status}】{title}")
            print(f"    📚 {course} | 📌 {task_types} | 📅 {due_str}\n")
    elif args.interactive:
        print("📋 EMBA 任務新增（互動模式）")
        name = input("任務名稱: ")
        course = input(f"課程 ({'/'.join(COURSE_MAP.values())}): ")
        task_type = input("類型 (課堂作業/小組發表/期中報告/期末報告): ")
        due = input("期限 (YYYY-MM-DD): ")
        desc = input("說明: ")
        add_task(name, course, task_type, due, desc)
    elif args.auto:
        results = detect_and_add_from_summary(args.auto, args.source)
        print(f"偵測到 {len(results)} 個任務")
    elif args.name:
        add_task(args.name, args.course, args.type, args.due, args.desc, args.source)
    else:
        print(__doc__)
