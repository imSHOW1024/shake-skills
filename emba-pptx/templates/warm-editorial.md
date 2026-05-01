# 模板：Warm Editorial（暖色卡片式技術解說風格）

**最適用於**：技術概念解說、演進歷程、抽象系統說明、科普型內容、影片/直播配合使用  
**風格定調**：親切有溫度、資訊密度中等、卡片浮動感、Notion 紙質美學  
**已驗證主題**：Harness Engineering（Prompt→Context→Harness 三代演進）  
**工具**：pptxgenjs + react-icons + sharp  
**座標系統**：`LAYOUT_WIDE`（13.33" × 7.5"）

---

## 配色系統

```javascript
const C = {
  bg:        "F5F0EB",  // 米白奶油（背景）
  grid:      "E8E3DA",  // 格線（30% 不透明）
  purple:    "8B5CF6",  // Prompt Engineering 強調色
  amber:     "F59E0B",  // Context Engineering 強調色
  blue:      "3B82F6",  // Harness Engineering 強調色
  coral:     "F87171",  // 問題/警告色
  green:     "10B981",  // 成功/正面色
  teal:      "0D9488",  // 標籤/膠囊用中性強調
  textDark:  "2D2417",  // 深暖棕（主文字）
  textMuted: "9B8EA0",  // 霧紫（次要文字）
  white:     "FFFFFF",  // 卡片底色
};
```

**Era 配色邏輯**：每個概念層/時代有專屬強調色，只用在關鍵詞和 icon 上，避免過度使用。

---

## 字型規格

| 層級 | 字型 | 尺寸 | 特殊 |
|------|------|------|------|
| 主標題 | Trebuchet MS Bold | 28–52pt | 關鍵詞以 era 色 inline 上色 |
| 副標題 | Calibri | 13–15pt | textMuted 色 |
| 卡片標題 | Trebuchet MS Bold | 16–20pt | textDark 色 |
| 卡片內文 | Calibri | 12–14pt | textMuted 色 |
| 膠囊標籤 | Calibri Bold | 10–12pt | era 色，置中 |

**不使用裝飾性底線** — 用文字本身的顏色做強調，不加底線。

---

## 背景 + 格線

```javascript
// 背景
slide.background = { color: "F5F0EB" };

// 細格線（選用，輕量感）
const spacing = 20 / 72; // 20pt → inches
for (let x = 0; x < 13.33; x += spacing) {
  slide.addShape("line", { x, y: 0, w: 0, h: 7.5,
    line: { color: "E8E3DA", width: 0.5 }, transparency: 70 });
}
for (let y = 0; y < 7.5; y += spacing) {
  slide.addShape("line", { x: 0, y, w: 13.33, h: 0,
    line: { color: "E8E3DA", width: 0.5 }, transparency: 70 });
}
```

---

## 核心元件

### 1. Shadow Factory（必須用 factory，不可重用物件）

```javascript
const makeShadow = () => ({
  type: "outer", color: "000000", blur: 8, offset: 2, angle: 135, opacity: 0.08
});
```

### 2. 白色卡片（帶可選左邊框或頂邊框）

```javascript
function addCard(slide, x, y, w, h, opts = {}) {
  const { borderColor, borderSide, borderW = 0.07, radius = 0.13,
          fill = "FFFFFF", shadow = true } = opts;

  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h,
    fill: { color: fill },
    line: { color: "E8E3DA", width: 0.5 },
    rectRadius: radius,
    shadow: shadow ? makeShadow() : { type: "none" },
  });

  // 左邊框（注意：需用 RECTANGLE，不是 ROUNDED_RECTANGLE）
  if (borderColor && borderSide === "left") {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: y + 0.05, w: borderW, h: h - 0.1,
      fill: { color: borderColor },
      line: { color: borderColor, width: 0 },
    });
  }
  // 頂邊框
  if (borderColor && borderSide === "top") {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.05, y, w: w - 0.1, h: borderW,
      fill: { color: borderColor },
      line: { color: borderColor, width: 0 },
    });
  }
}
```

### 3. 膠囊標籤（Pill Tag）

```javascript
function addPill(slide, x, y, w, h, text, color, opts = {}) {
  const { fontSize = 10 } = opts;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h,
    fill: { color, transparency: 88 },
    line: { color, width: 1, transparency: 60 },
    rectRadius: h / 2,  // ← 全圓角關鍵
  });
  slide.addText(text, {
    x, y, w, h,
    fontSize, bold: true, color,
    align: "center", valign: "middle", margin: 0,
  });
}
```

### 4. Icon Badge（圓角方形背景 + react-icon）

```javascript
// 安裝：npm install react react-dom react-icons sharp
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

async function iconB64(IconComponent, hexColor, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color: "#" + hexColor, size: String(size) })
  );
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

async function addIconBadge(slide, IconComp, color, bx, by, bSize = 0.56) {
  const icoData = await iconB64(IconComp, color, 256);
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: bx, y: by, w: bSize, h: bSize,
    fill: { color, transparency: 85 },
    line: { color, width: 0.5 },
    rectRadius: 0.1,
  });
  const pad = bSize * 0.15;
  slide.addImage({
    data: icoData,
    x: bx + pad, y: by + pad,
    w: bSize - pad * 2, h: bSize - pad * 2
  });
}
```

### 5. 同心圓圖（2層或3層）

```javascript
// 3層同心圓：外(blue) → 中(amber) → 內(purple)
// 建議比例：外 6.5×6.1", 中 4.3×4.55", 內 2.3×2.95"（左側置中）

slide.addShape(pres.shapes.OVAL, {
  x: 1.5, y: 0.95, w: 6.5, h: 6.1,
  fill: { color: C.blue, transparency: 93 },
  line: { color: C.blue, width: 2.5 },
});
slide.addShape(pres.shapes.OVAL, {
  x: 2.6, y: 1.75, w: 4.3, h: 4.55,
  fill: { color: C.amber, transparency: 90 },
  line: { color: C.amber, width: 2 },
});
slide.addShape(pres.shapes.OVAL, {
  x: 3.6, y: 2.55, w: 2.3, h: 2.95,
  fill: { color: C.purple, transparency: 88 },
  line: { color: C.purple, width: 2 },
});
```

---

## 版型庫（Slide Pattern Library）

| 版型名稱 | 用途 | 關鍵元件 |
|---------|------|---------|
| `cover-with-pill-tag` | 封面 | 膠囊標籤 + 大標題（雙色）+ 側邊裝飾條 |
| `two-column-card-comparison` | 對比兩件事 | 左右各一大卡，VS 文字居中 |
| `three-icon-row` | 並列三項 | 三等份卡片，各有 icon badge |
| `stat-callout-card` | 單一大數字 | 置中卡片 + 超大數字 + icon |
| `three-era-horizontal-flow` | 演進歷程 | 三卡帶頂邊框 + 箭頭連接 |
| `two-section-vertical-split` | 概念對比 | 上下兩大卡，各有左邊框 + 膠囊標籤 |
| `nested-concentric-circles` | 包含關係 | 2層或3層同心橢圓 + 右側摘要卡 |
| `checklist-with-summary` | 定義+行動清單 | 5列白色行卡 + 底部藍底摘要卡 |
| `two-column-input-execution` | 問題分層 | 左側清單卡 + 右側衝突視覺 |
| `failure-curve-annotation` | 折線+標記 | line shapes 折線 + 標記圓點 + 文字卡 |
| `closing-single-statement` | 結語 | 超大居中文字 + 小 icon 行 + 底部膠囊 |

---

## 敘事弧（技術演進主題標準 15 頁結構）

```
封面 → 問題鉤子(對比) → 已嘗試但失敗 → 問題依然存在
→ 頓悟/洞察 → 議程 → 概念 A 定義 → 概念 A 遇到天花板
→ 概念 A vs B 對比 → 概念 B 包含概念 A（同心圓）
→ 真實執行中的失敗 → 問題分層（輸入側 vs 執行側）
→ 概念 C 完整定義（checklist）→ 三層嵌套收束 → 結語
```

---

## 安裝與環境

```bash
cd ~/Documents/emba-pptx-output
npm init -y
npm install pptxgenjs react react-dom react-icons sharp
```

輸出目錄：`~/Documents/emba-pptx-output/output/`  
輸出檔名建議：`{主題}-{日期}.pptx`

---

## 製作紀錄

| 版本 | 日期 | 主題 | 頁數 |
|------|------|------|------|
| v1.0 | 2026-04 | Harness Engineering（Prompt→Context→Harness） | 15頁 |
