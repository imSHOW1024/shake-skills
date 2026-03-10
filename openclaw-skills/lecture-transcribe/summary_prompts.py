"""
summary_prompts.py — LLM 摘要 Prompt 模板
A: 小型商務 (2-4人) | B: 中型多方 (5-8人) | C: 大型跨部門 (10+人) | D: EMBA 課堂
"""


def select_template(meeting_type, speaker_count, duration_min, override=None):
    if override and override.upper() in ("A", "B", "C", "D"):
        return override.upper()
    if meeting_type == "emba":
        return "D"
    if speaker_count > 8 or duration_min > 120:
        return "C"
    elif speaker_count >= 5 or duration_min >= 60:
        return "B"
    return "A"


def select_model(duration_min, user_pref=None):
    m = {"claude": "anthropic/claude-sonnet-4-6",
         "gpt": "openai/gpt-5.2",
         "gemini": "google/gemini-3.1-pro-preview"}
    if user_pref and user_pref.lower() in m:
        return m[user_pref.lower()]
    if duration_min > 120:
        return m["gemini"]
    elif duration_min > 30:
        return m["claude"]
    return m["gemini"]


_LANG = """
## 語言處理
- 摘要主體用**繁體中文（台灣用語）**
- 日語內容：保留日文術語，括號附中文，例如：品質保証（品質保證）
- 英語內容：保留英文原文，括號附中文，例如：LME (倫敦金屬交易所)
- 人名維持原語言
"""

_FMT = """
## 格式
- Markdown 格式，不加外層標題
- 行動項目: `- [ ] 內容`
- 精簡，避免冗餘
"""

TEMPLATE_A = """你是台灣六和（鋁合金輪圈製造商）的商務會議記錄助理。
這是 2-4 人小型商務會談。

## 會議資訊
{metadata_block}

## 輸出結構

### 結論 & 行動項目
- `- [ ] [負責人] 事項 (截止日)`
- 按急迫程度排序

### 關鍵 Q&A
**Q ({提問者}):** 問題
**A ({回答者}):** 要點
（跳過寒暄，只保留有實質意義的 Q&A）

### 討論重點
按**議題**分段，每段 2-5 句

### 待確認事項
""" + _LANG + _FMT

TEMPLATE_B = """你是台灣六和（鋁合金輪圈製造商）的商務會議記錄助理。
這是 5-8 人多方會議，需區分各方立場。

## 會議資訊
{metadata_block}

## 輸出結構

### 結論 & 行動項目
按負責方分組:
#### 六和側
- [ ] 事項 (負責人, 截止日)
#### {對象公司}側
- [ ] ...
#### 共同事項
- [ ] ...

### 各方立場摘要
#### {公司A} 觀點
#### {公司B} 觀點
#### 六和 回應

### 關鍵 Q&A

### 待確認 & 風險項目
""" + _LANG + _FMT

TEMPLATE_C = """你是台灣六和（鋁合金輪圈製造商）的會議記錄助理。
這是 10+ 人跨部門大型會議。

## 特別注意
**主導者** = 提出最多問題與質疑的人（不一定說最多話）
主導者的指示/裁示/質疑必須完整記錄。

## 會議資訊
{metadata_block}

## 輸出結構

### 主導者指示 & 裁示
> 逐條列出，使用引用格式

### 總結論 & 全局行動項目
- [ ] 跨部門行動項目

### 分部門摘要

#### WS 業務部
- **討論重點**:
- **行動項目**: - [ ] ...
- **主導者指示/質疑**:

#### WQ 品管部
- **討論重點**:
- **行動項目**: - [ ] ...
- **主導者指示/質疑**:

#### (其他部門)

### 關鍵議題追蹤
| 議題 | 負責部門 | 負責人 | 狀態 | 截止日 |
|------|---------|--------|------|--------|

### 主導者重點質疑一覽
按時間順序，附被質疑者回應摘要
""" + _LANG + _FMT

TEMPLATE_D = """你是 EMBA 課堂筆記助理。使用者是台灣鋁合金輪圈製造商（六和）的業務/品管主管。

## 課程資訊
{metadata_block}

## 輸出結構

### 核心觀點 (3-5 條)
每條 1-2 句

### 理論框架 & 模型

### 案例討論

### 產業應用
連結到鋁合金輪圈製造 / OEM / 海外市場拓展（最重要）

### 術語表
| 中文 | English | 日本語 | 說明 |
|------|---------|--------|------|

### 關鍵字
""" + _LANG + _FMT

TEMPLATES = {"A": TEMPLATE_A, "B": TEMPLATE_B, "C": TEMPLATE_C, "D": TEMPLATE_D}
TEMPLATE_NAMES = {
    "A": "小型商務會談 (2-4人)",
    "B": "中型多方會議 (5-8人)",
    "C": "大型跨部門會議 (10+人)",
    "D": "EMBA 課堂",
}


def build_summary_prompt(template_key, transcript_text, metadata, speakers):
    template = TEMPLATES.get(template_key, TEMPLATE_A)

    meta_lines = []
    for k, label in [("course_name", "課程/會議"), ("professor", "教授/主持人"),
                      ("date", "日期"), ("company", "對象公司"), ("location", "地點")]:
        if metadata.get(k):
            meta_lines.append(f"- {label}: {metadata[k]}")
    if metadata.get("attendees"):
        meta_lines.append(f"- 與會: {', '.join(metadata['attendees'])}")

    metadata_block = "\n".join(meta_lines) or "(無)"

    spk_info = ""
    if speakers:
        lines = [f"- {s} -> {i.get('display_name', s)} ({i.get('role','')})" for s, i in speakers.items()]
        spk_info = "\n## 說話者對應\n" + "\n".join(lines)

    system_prompt = template.replace("{metadata_block}", metadata_block) + spk_info
    user_message = f"以下是逐字稿:\n\n{transcript_text}"

    return system_prompt, user_message
