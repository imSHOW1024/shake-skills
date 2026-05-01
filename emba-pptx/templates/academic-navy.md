# 模板：Academic Navy（學術商管標準版）

**最適用於**：EMBA 課堂報告、個案分析、正式管理簡報、學術論文口報  
**風格定調**：沉穩、專業、資訊密度中高、適合有評分標準的正式場合  
**已驗證課程**：企業危機管理（v1.0）

---

## 配色系統

| 角色 | 色碼 | 用途 |
|------|------|------|
| primary | `1E2761` 深海軍藍 | 主色，佔 60% |
| secondary | `CADCFC` 冰藍 | 輔助色 |
| accent | `FFFFFF` 白色 | 強調、文字 |
| crisis | `E8601C` 警示橘 | 危機/問題類 |
| recovery | `2E7D32` 深綠 | 轉機/解決類 |
| neutral | `6B7C8A` 灰藍 | 補充/說明類 |
| surface | `F5F7FA` | 內容頁底色 |
| muted | `888888` | 輔助小字 |

**Sandwich 結構**（建立視覺呼吸感）：
- 封面 / 結語 → 深色底 `1E2761`
- 所有內容頁 → 淺色底 `F5F7FA`

---

## 字型配對

| 用途 | 首選 | Fallback |
|------|------|---------|
| 標題 | Poppins Bold | Arial Black |
| 內文 | Lora | Calibri |
| 小字 | Lora Italic | Calibri Light |

## 字型尺寸規範

| 層級 | 尺寸 |
|------|------|
| 封面主標 | 32–36pt |
| 頁面標題 | 24–28pt |
| 卡片標題 | 13–14pt Bold |
| 卡片內文 | 12–13pt |
| 輔助小字 | 10–11pt |
| 浮水印 | 9–10pt `999999` |

---

## 每頁共用元素

左下角浮水印（`x:0.2 y:5.35 w:6 h:0.2`）：  
`{課程名稱} {作業類型}｜{學期}` — `999999`，9pt，Lora Italic

---

## 卡片元件（pptxgenjs 原生，保持可編輯）

所有卡片 = `addShape` 底層矩形 + `addText` 疊加。

⚠️ **重要**：`ROUNDED_RECTANGLE` 不可搭配頂部矩形色條（圓角無法被覆蓋），請改用 `RECTANGLE`。

### A型｜問題/危機卡片

```javascript
// 底層白色卡片
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
| 危機版 | `FFF0E6` | `E8601C` | 問題根源、過去做法 |
| 轉機版 | `E8F5E9` | `2E7D32` | 解決方案、未來方向 |
| 補充版 | `EEF2FF` | `1E2761` | 說明、代價、補充 |

無外框線，同 A型結構但無 `line`。

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

## 座標系統

`LAYOUT_16x9`（10" × 5.625"）
