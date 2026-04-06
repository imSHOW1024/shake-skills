---
name: emba-pptx
description: >
  製作 EMBA 課程作業 PowerPoint 簡報（.pptx）的完整工作流程 skill。
  涵蓋：商管學院風格設計、課程框架視覺化、卡片式版面、圖表嵌入、QA 驗證。
  當使用者提到 EMBA 課程、作業簡報、期中報告、期末報告、商管簡報、pptx、deck、
  slides、presentation，或說「幫我做一份簡報」「做 PPT」「做投影片」時，務必啟用此 skill。
  同時適用於：課程個案分析、小組報告、管理顧問風格簡報。
  本 skill 會隨每次製作經驗持續更新優化。
---

# EMBA PPTX Skill

## 快速索引

| 需求 | 參考位置 |
|------|---------|
| 設計規格、配色、字型 | 本文 §設計系統 |
| 卡片元件語法 | 本文 §卡片元件 |
| 各課程風格差異 | references/course-styles.md |
| 商管框架正確用法 | references/frameworks.md |
| 完整製作流程 | 本文 §工作流程 |
| 歷次製作心得 | references/lessons-learned.md |

---

## 工作流程（每次製作必須依序執行）

### Phase 0｜Skill 讀取
依序讀取：
1. `pptx` SKILL.md → 繼續讀 `pptxgenjs.md`
2. 本 skill 的 `references/frameworks.md`（若簡報用到商管框架）
3. 本 skill 的 `references/course-styles.md`（對應課程類型）

讀完回報「✅ Skills loaded」再動工。

### Phase 1｜框架驗證（重要）
製作前主動確認使用的商管分析框架：
- 對照 `references/frameworks.md` 核對正確用法
- 告知使用者：「這份簡報用到 [框架名]，正確用法是 [說明]，我會按此呈現」
- 若使用者的框架應用有誤，提醒並建議修正方向
- **不得直接套用框架而不驗證正確性**

### Phase 2｜環境確認
```bash
# Python：使用專案 venv（3.12），避免系統 3.9）
# 若無 venv，以 Homebrew 的 python3.12 建立：
/opt/homebrew/bin/python3.12 -m venv ~/Documents/emba-pptx-output/.venv
~/Documents/emba-pptx-output/.venv/bin/pip install matplotlib numpy

# Node + pptxgenjs（本地安裝，不依賴 global）
cd ~/Documents/emba-pptx-output
npm init -y && npm install pptxgenjs

# 建立輸出目錄
mkdir -p ~/Documents/emba-pptx-output/output
mkdir -p ~/Documents/emba-pptx-output/assets
```

### Phase 3｜圖片策略（開工前決定）
| 類型 | 做法 |
|------|------|
| AI 氛圍背景圖 | Placeholder 模式，附 Gemini Prompt |
| 精確圖表（四象限、矩陣） | matplotlib 產 PNG 嵌入，用 `.venv/bin/python3.12` 執行 |
| Icon / 裝飾 | Unicode emoji + pptxgenjs `addShape` |
| 流程圖 | Mermaid → PNG 嵌入 |

Placeholder 格式統一：
```
矩形 fill #3A3A3A + 白字 12pt
[IMAGE PLACEHOLDER] {用途}
建議尺寸：{W}×{H}px
Gemini Prompt：{附在文末}
```

### Phase 4｜製作
依 `pptxgenjs.md` 規範撰寫，座標系統：`LAYOUT_16x9`（10" × 5.625"）
套用本 skill §設計系統 的配色與字型。

### Phase 5｜QA（不可省略）
```bash
# 文字驗證
python -m markitdown output.pptx

# 殘留佔位符
python -m markitdown output.pptx | grep -iE "TODO|lorem|ipsum|\[insert"

# 視覺轉圖
/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --convert-to pdf output.pptx
/opt/homebrew/bin/pdftoppm -jpeg -r 150 output.pdf slide
# → subagent 逐頁視覺審查：重疊、溢出、低對比、對齊問題
```
至少完成一輪 fix-and-verify 才可宣告完成。

---

## 設計系統

### 配色主題（商管學院標準版）

| 角色 | 色碼 | 用途 |
|------|------|------|
| primary | `#1E2761` 深海軍藍 | 主色，佔 60% |
| secondary | `#CADCFC` 冰藍 | 輔助色 |
| accent | `#FFFFFF` 白色 | 強調、文字 |
| crisis | `#E8601C` 警示橘 | 危機/問題類 |
| recovery | `#2E7D32` 深綠 | 轉機/解決類 |
| neutral | `#6B7C8A` 灰藍 | 補充/說明類 |
| surface | `#F5F7FA` | 內容頁底色 |
| muted | `#888888` | 輔助小字 |

**Sandwich 結構**（視覺呼吸感）：
- 封面 / 結語 → 深色底 `#1E2761`
- 內容頁 → 淺色底 `#F5F7FA`

### 字型配對

| 用途 | 首選 | Fallback |
|------|------|---------|
| 標題 | Poppins Bold | Arial Black |
| 內文 | Lora | Calibri |
| 小字 | Lora Italic | Calibri Light |

### 字型尺寸規範

| 層級 | 尺寸 |
|------|------|
| 封面主標 | 32–36pt |
| 頁面標題 | 24–28pt |
| 卡片標題 | 13–14pt Bold |
| 卡片內文 | 12–13pt |
| 輔助小字 | 10–11pt |
| 浮水印 | 9–10pt `#999999` |

### 每頁共用元素
左下角浮水印（`x:0.2 y:5.35 w:6 h:0.2`）：
`{課程名稱} {作業類型}｜{學期}` — `#999999`，9pt，Lora Italic

---

## 卡片元件（pptxgenjs 原生，保持可編輯）

所有卡片 = `addShape` 底層矩形 + `addText` 疊加。

⚠️ **重要**：`ROUNDED_RECTANGLE` 不可搭配頂部矩形色條（圓角無法被覆蓋），請改用 `RECTANGLE`。詳見 `pptxgenjs.md` §Common Pitfalls。

### A型｜問題/危機卡片

```javascript
// 底層白色卡片（使用 RECTANGLE，不用 ROUNDED_RECTANGLE）
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: 'FFFFFF' },
  line: { color: 'DDDDDD', width: 1 }
});
// 頂部橘色色條 h:0.28"
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h: 0.28,
  fill: { color: 'E8601C' },
  line: { color: 'E8601C', width: 0 }
});
// 色條標題（白色 11pt Bold margin:0）
slide.addText('標題', {
  x: x+0.12, y: y+0.04, w: w-0.18, h: 0.24,
  fontSize: 11, bold: true, fontFace: 'Arial Black',
  color: 'FFFFFF', valign: 'middle', margin: 0
});
// 內文（12–13pt #333333 行距 1.3）
slide.addText('內文...', {
  x: x+0.12, y: y+0.38, w: w-0.22, h: h-0.46,
  fontSize: 12, color: '333333', fontFace: 'Calibri',
  valign: 'top', lineSpacingMultiple: 1.3
});
```

### B型｜對比/轉機卡片

| 變體 | 底色 | 頂條色 | 用途 |
|------|------|--------|------|
| 危機版 | `#FFF0E6` | `#E8601C` | 問題根源、過去做法 |
| 轉機版 | `#E8F5E9` | `#2E7D32` | 解決方案、未來方向 |
| 補充版 | `#EEF2FF` | `#1E2761` | 說明、代價、補充 |

無外框線，同 A型結構但無邊線。

### C型｜引用框（金句）

```javascript
// 深藍底色
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h, fill: { color: '1E2761' },
  line: { color: '1E2761', width: 0 }
});
// 左側白色垂直線（w:0.04"）
slide.addShape(pres.shapes.RECTANGLE, {
  x, y: y+0.06, w: 0.04, h: h-0.12,
  fill: { color: 'FFFFFF' },
  line: { color: 'FFFFFF', width: 0 }
});
// 白色 Italic 文字
slide.addText('"金句內容"', {
  x: x+0.16, y, w: w-0.2, h,
  fontSize: 14, italic: true, color: 'FFFFFF',
  fontFace: 'Calibri', align: 'center', valign: 'middle'
});
```

---

## Gemini 圖片生成 Prompt 模板

### 封面背景（通用）
```
Dark cinematic {產業/主題} scene at night,
dramatic high-contrast professional lighting,
no text, no people, no logos, photorealistic,
16:9 aspect ratio, 1920x1080px,
suitable as dark presentation background at 40% opacity
```

### 概念示意圖（通用）
```
Abstract {概念} visualization, {配色描述},
clean modern minimal design,
no text, no labels, no country names,
white or light background, 16:9 aspect ratio,
suitable for business strategy presentation
```

---

## 課程風格對照

詳見 `references/course-styles.md`。

| 課程類型 | 主色調建議 | 核心框架 |
|---------|-----------|---------|
| 危機管理 | 深藍+警示橘 | PEST、四象限、三階段 |
| 策略管理 | 深藍+金色 | SWOT、五力、商業模式圖 |
| 跨文化研究 | 深藍+暖橘 | Hofstede 維度、文化比較矩陣 |
| 個案研討 | 深藍+綠色 | 個案問題結構、決策樹 |
| 消費者行為 | 深藍+柔紫 | 顧客旅程、決策流程 |

---

## 更新記錄

| 版本 | 日期 | 更新內容 |
|------|------|---------|
| v1.0 | 2026-04 | 初版，基於企業危機管理期中報告製作經驗 |

每次製作完成後，追加版本記錄，並更新 `references/lessons-learned.md`。
