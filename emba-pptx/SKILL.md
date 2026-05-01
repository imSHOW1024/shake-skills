---
name: emba-pptx
description: >
  製作 PowerPoint 簡報（.pptx）的完整工作流程 skill，支援多種視覺模板。
  涵蓋：EMBA 課堂報告、個案分析、技術概念解說、管理簡報、課程作業。
  內建三套完整模板：
    mckinsey-mono（黑白灰麥肯錫風、個人一致風格、期末重大報告首選）、
    academic-navy（學術商管標準版）、
    warm-editorial（暖色卡片式技術解說）。
  當使用者提到 EMBA 課程、作業簡報、期中報告、期末報告、商管簡報、pptx、deck、slides、
  presentation，或說「幫我做一份簡報」「做 PPT」「做投影片」「解說 X 概念」時，務必啟用此 skill。
  同時適用於：課程個案分析、小組報告、管理顧問風格簡報、技術演進說明。
  本 skill 會隨每次製作經驗持續更新優化。
---

# EMBA PPTX Skill

## 快速索引

| 需求 | 參考位置 |
|------|---------|
| **選擇哪個模板** | `templates/template-selector.md` |
| 黑白灰麥肯錫風格規格（期末首選） | `templates/mckinsey-mono.md` |
| 學術商管風格規格 | `templates/academic-navy.md` |
| 暖色技術解說風格規格 | `templates/warm-editorial.md` |
| pptxgenjs 語法參考 | `pptx` skill → `pptxgenjs.md` |
| 各課程風格差異 | `references/course-styles.md` |
| 商管框架正確用法 | `references/frameworks.md` |
| 歷次製作心得 | `references/lessons-learned.md` |

---

## 工作流程（每次製作必須依序執行）

### Phase 0｜Skill 讀取 + 模板選擇

1. 讀取 `pptx` SKILL.md → 繼續讀 `pptxgenjs.md`
2. 讀取 `templates/template-selector.md`
3. **詢問使用者 2 個問題**（模板選擇器中定義），確認模板後讀取對應模板文件
4. 讀完回報「✅ Skills loaded，使用模板：{模板名稱}」再動工

### Phase 1｜框架驗證（academic-navy 時適用）

製作前主動確認使用的商管分析框架：
- 對照 `references/frameworks.md` 核對正確用法
- 告知使用者：「這份簡報用到 [框架名]，正確用法是 [說明]，我會按此呈現」
- 若使用者的框架應用有誤，提醒並建議修正方向
- **不得直接套用框架而不驗證正確性**

### Phase 2｜環境確認

```bash
# 建立輸出目錄
mkdir -p ~/Documents/emba-pptx-output/output

# Node + pptxgenjs（本地安裝，不依賴 global）
cd ~/Documents/emba-pptx-output
npm init -y && npm install pptxgenjs

# warm-editorial 額外需要：
npm install react react-dom react-icons sharp

# Python（圖表用）：使用專案 venv（3.12），避免系統 3.9
/opt/homebrew/bin/python3.12 -m venv ~/Documents/emba-pptx-output/.venv
~/Documents/emba-pptx-output/.venv/bin/pip install matplotlib numpy
```

### Phase 3｜圖片策略（開工前決定）

| 類型 | 做法 |
|------|------|
| AI 氛圍背景圖 | Placeholder 模式，附 Gemini Prompt（academic-navy 模板有範本） |
| 精確圖表（四象限、矩陣） | matplotlib 產 PNG 嵌入，用 `.venv/bin/python3.12` 執行 |
| Icon / 徽章 | react-icons → sharp → base64 PNG（warm-editorial 模板有 `iconB64` 函式） |
| 流程圖 | Mermaid → PNG 嵌入 |

Placeholder 格式統一：
```
矩形 fill #3A3A3A + 白字 12pt
[IMAGE PLACEHOLDER] {用途}
建議尺寸：{W}×{H}px
Gemini Prompt：{附在文末}
```

### Phase 4｜製作

依 `pptxgenjs.md` 規範撰寫，座標系統依模板而異：
- **academic-navy**：`LAYOUT_16x9`（10" × 5.625"）
- **warm-editorial**：`LAYOUT_WIDE`（13.33" × 7.5"）

套用所選模板的配色、字型、卡片元件語法。

### Phase 5｜QA（不可省略）

```bash
# 文字驗證
python -m markitdown output.pptx

# 殘留佔位符
python -m markitdown output.pptx | grep -iE "TODO|lorem|ipsum|\[insert|PLACEHOLDER"

# 視覺轉圖
/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --convert-to pdf output.pptx --outdir ./
/opt/homebrew/bin/pdftoppm -jpeg -r 150 output.pdf slide
# → subagent 逐頁視覺審查：重疊、溢出、低對比、對齊問題
```

至少完成一輪 fix-and-verify 才可宣告完成。

---

## 可用模板

### 1. mckinsey-mono（黑白灰麥肯錫風格）

讀取：`templates/mckinsey-mono.md`

- **適用**：EMBA 期末報告、重大個案報告、論文解析、任何需要「個人一致風格」的正式簡報
- **特色**：純黑白灰配色、麥肯錫大標題驅動、卡片狀態系統（實線/虛線/灰底/黑底）、底部金句收尾
- **座標**：LAYOUT_16x9（10" × 5.625"）
- **已驗證**：1141電子化企業期末報告、1141資本決策期末報告

### 2. academic-navy（學術商管標準版）

讀取：`templates/academic-navy.md`

- **適用**：EMBA 課堂報告、個案分析、正式管理簡報
- **特色**：深海軍藍 Sandwich 結構、A/B/C 三型卡片、matplotlib 圖表整合
- **座標**：LAYOUT_16x9（10" × 5.625"）
- **已驗證**：企業危機管理期中報告（v1.0）

### 3. warm-editorial（暖色卡片式技術解說）

讀取：`templates/warm-editorial.md`

- **適用**：技術概念解說、演進歷程、抽象系統說明、科普內容
- **特色**：米白奶油底、浮動白卡、era 強調色、react-icons 徽章
- **座標**：LAYOUT_WIDE（13.33" × 7.5"）
- **已驗證**：Harness Engineering 三代演進（v1.0，15頁）

---

## 更新記錄

| 版本 | 日期 | 更新內容 |
|------|------|---------|
| v1.0 | 2026-04 | 初版，academic-navy 基於企業危機管理期中報告 |
| v1.1 | 2026-04 | 新增 warm-editorial 模板；重構為多模板架構 |
| v1.2 | 2026-04 | 新增 mckinsey-mono 模板；基於電子化企業+資本決策兩份期末報告實體 PDF 萃取風格 |

每次製作完成後，追加版本記錄，並更新 `references/lessons-learned.md`。
