# 模板：McKinsey Mono（黑白灰麥肯錫風格）

**最適用於**：EMBA 課程期末報告、重大個案報告、學術論文解析、任何需要「個人一致風格」的正式簡報  
**風格定調**：黑白灰為唯一配色、麥肯錫式大標題驅動、卡片式內文、底部金句收尾、商務專業簡潔俐落  
**已驗證課程**：1141電子化企業（期末報告）、1141資本決策（期末報告）

---

## 設計哲學

此模板源自使用者蔡翔宇的個人簡報風格，具有以下核心原則：

1. **標題即論點**：每頁標題直接說結論，不用「關於XXX」之類模糊標題
2. **卡片是容器不是裝飾**：卡片邊框粗細、填色深淺代表內容的「狀態」與「重要性」
3. **底部金句是收尾拳**：每頁最後一行是整頁最重要的一句話
4. **黑白灰不是貧乏**：透過填色層次（純白 → 淺灰 → 深灰 → 純黑）製造視覺張力
5. **少 AI 味**：不用過度對稱、不塞滿每個角落、留白是設計的一部分

---

## 配色系統

| 角色 | 色碼 | 用途 |
|------|------|------|
| bg | `FFFFFF` 純白 | 所有頁面底色 |
| text-primary | `1A1A1A` 近黑 | 標題、主要文字 |
| text-secondary | `555555` 深灰 | 一般內文 |
| text-muted | `999999` 淺灰 | 標籤、頁碼、來源注記 |
| border-strong | `1A1A1A` 近黑 | 實線卡片邊框（主要）|
| border-light | `AAAAAA` 中灰 | 虛線卡片邊框（次要/未完成）|
| fill-gray-light | `EEEEEE` 淺灰 | 次要卡片底色 |
| fill-gray-mid | `CCCCCC` 中灰 | 強調用灰色底 |
| fill-black | `1A1A1A` 近黑 | 核心強調卡片底色 |
| rule | `CCCCCC` 淡灰 | 分隔線（標題下方、底部金句上方）|
| accent-bar | `1A1A1A` | 左側強調豎線（3-4px） |

**⚠️ 禁止使用任何彩色**：無藍、無橘、無紅、無綠。唯一「色彩」是黑白灰的層次。

---

## 字型配對

| 用途 | 首選 | Fallback |
|------|------|---------|
| 標題（中文） | Noto Sans TC Bold / PingFang TC Bold | Arial Black |
| 內文（中文） | Noto Sans TC Regular | Arial |
| 英文混排 | Arial / Helvetica | Calibri |
| 小字注記 | Noto Sans TC Light | Calibri Light |

## 字型尺寸規範

| 層級 | 尺寸 | 字重 | 顏色 |
|------|------|------|------|
| 封面主標 | 36–42pt | Bold | `1A1A1A` |
| 封面副標 | 18–22pt | Regular | `555555` |
| 頁面主標題 | 28–32pt | Bold | `1A1A1A` |
| 頁面副標題（｜後） | 20–24pt | Regular | `555555` |
| 頂部 Header 課程名 | 10pt | Regular | `888888` |
| 頂部 Header 報告類型 | 10pt | Bold | `1A1A1A` |
| 卡片標題 | 12–14pt | Bold | `1A1A1A` |
| 卡片內文 | 11–13pt | Regular | `555555` |
| 底部金句 | 12–13pt | Regular/Bold | `1A1A1A` |
| 來源注記 | 9–10pt | Italic | `999999` |
| 頁碼 | 12–14pt | Regular | `AAAAAA` |

---

## 座標系統

`LAYOUT_16x9`（10" × 5.625"）

安全邊距：左右 `0.4"`，上 `0.3"`，下 `0.25"`

---

## 每頁共用元素

### 頂部 Header 區（封面 + 內容頁皆有）

```javascript
// 課程名稱（左）
slide.addText('1141電子化企業', {
  x: 0.4, y: 0.1, w: 4, h: 0.2,
  fontSize: 10, color: '888888', fontFace: 'Arial', bold: false
});

// 報告類型（右）
slide.addText('期末報告', {
  x: 6, y: 0.1, w: 3.6, h: 0.2,
  fontSize: 10, color: '1A1A1A', fontFace: 'Arial', bold: true, align: 'right'
});

// 分隔線（貫穿全寬）
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 0.34, w: 9.2, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});
```

### 頁碼（右下角）

```javascript
slide.addText(String(slideNum), {
  x: 8.9, y: 5.35, w: 0.7, h: 0.2,
  fontSize: 13, color: 'AAAAAA', fontFace: 'Arial', align: 'right'
});
```

### 底部來源注記（左下角，可選）

```javascript
slide.addText('— 注記文字', {
  x: 0.4, y: 5.3, w: 7, h: 0.2,
  fontSize: 9, italic: true, color: '999999', fontFace: 'Arial'
});
```

---

## 頁面結構模式

### 封面頁

```
┌─ 課程名稱（左10pt灰）─────────────── 期末報告（右10pt黑粗）─┐
│ ─────────────────────────────────────────────────────────── │
│                                                             │
│  [主標題 大粗黑 36-42pt 左對齊 佔2-3行]                     │
│                                                             │
│    —  副標題或個案名（20pt 灰 縮排）                         │
│                                                             │
│  ────────────────                                           │
│  原著指導教授    原著研究生（或 課程資訊）                   │
│  姓名（粗）      姓名（粗）                                  │
│  ────────────────                                           │
│  學號 姓名                                                  │
└─────────────────────────────────────────────────────────── ┘
```

```javascript
// 封面主標題
slide.addText('B2B傳統製造業的\n客戶關係與非結構化資訊管理：\n從電子化流程到管理實務的觀察', {
  x: 0.4, y: 0.7, w: 9.2, h: 2.8,
  fontSize: 36, bold: true, color: '1A1A1A', fontFace: 'Arial Black',
  valign: 'top', lineSpacingMultiple: 1.25
});

// 副標題（em dash 格式）
slide.addText('—  以汽車零組件製造商 L 社為例', {
  x: 0.8, y: 3.6, w: 9, h: 0.4,
  fontSize: 20, color: '555555', fontFace: 'Arial', valign: 'middle'
});

// 分隔線
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 4.1, w: 3.5, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});

// 作者資訊（兩欄）
slide.addText('原著指導教授', { x: 0.4, y: 4.15, w: 4, h: 0.18, fontSize: 9, color: '888888', fontFace: 'Arial' });
slide.addText('廖本哲博士', { x: 0.4, y: 4.33, w: 4, h: 0.25, fontSize: 14, bold: true, color: '1A1A1A', fontFace: 'Arial' });

slide.addText('原著研究生', { x: 4.5, y: 4.15, w: 4, h: 0.18, fontSize: 9, color: '888888', fontFace: 'Arial' });
slide.addText('劉傑耀', { x: 4.5, y: 4.33, w: 4, h: 0.25, fontSize: 14, bold: true, color: '1A1A1A', fontFace: 'Arial' });

// 報告人資訊（底部）
slide.addText('報告人：蔡翔宇 11491638\n授課教授：廖本哲博士', {
  x: 0.4, y: 5.0, w: 7, h: 0.4,
  fontSize: 10, color: '888888', fontFace: 'Arial', lineSpacingMultiple: 1.5
});
```

---

### 內容頁標題區

**格式A：純標題**
```javascript
slide.addText('企業背景與研究情境', {
  x: 0.4, y: 0.42, w: 9.2, h: 0.6,
  fontSize: 30, bold: true, color: '1A1A1A', fontFace: 'Arial Black', valign: 'middle'
});
// 標題下分隔線
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 1.05, w: 9.2, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});
```

**格式B：標題｜副標題（同行）**
```javascript
slide.addText('研究架構說明｜以TAM模式作為分析基礎', {
  x: 0.4, y: 0.42, w: 9.2, h: 0.6,
  fontSize: 26, bold: true, color: '1A1A1A', fontFace: 'Arial Black', valign: 'middle'
});
```

**格式C：標題 + 第二行副標（置中小字）**
```javascript
// 主標題
slide.addText('操作型定義說明｜概念如何轉換為問卷題項', {
  x: 0.4, y: 0.42, w: 9.2, h: 0.55,
  fontSize: 26, bold: true, color: '1A1A1A', fontFace: 'Arial Black', valign: 'middle'
});
// 副說明（括號小字）
slide.addText('（操作型定義 是將 概念型定義 轉換為具體可衡量的指標）', {
  x: 0.4, y: 0.98, w: 9.2, h: 0.2,
  fontSize: 10, color: '888888', fontFace: 'Arial', valign: 'middle'
});
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 1.22, w: 9.2, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});
```

---

## 卡片元件

### Card-S｜實線框卡（主要內容，狀態：現況/已完成）

```javascript
// 白底 + 1pt 深色實線框
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: 'FFFFFF' },
  line: { color: '1A1A1A', width: 1.5 }
});
// 小標籤（可選，灰色 9pt）
slide.addText('標籤文字', {
  x: x+0.15, y: y+0.12, w: w-0.3, h: 0.2,
  fontSize: 9, color: '888888', fontFace: 'Arial'
});
// 卡片標題
slide.addText('ERP (Oracle EBS)', {
  x: x+0.15, y: y+0.32, w: w-0.3, h: 0.28,
  fontSize: 13, bold: true, color: '1A1A1A', fontFace: 'Arial'
});
// 卡片內文
slide.addText('核心交易系統：財務、生產、庫存、訂單', {
  x: x+0.15, y: y+0.62, w: w-0.3, h: h-0.72,
  fontSize: 11, color: '555555', fontFace: 'Arial', valign: 'top',
  lineSpacingMultiple: 1.3
});
```

### Card-D｜虛線框卡（次要/未來/未確定狀態）

```javascript
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: 'FFFFFF' },
  line: { color: 'AAAAAA', width: 1, dashType: 'dash' }
});
// 標題用灰色（表示「尚未到達」）
slide.addText('Digital Transformation\n數位轉型', {
  x: x+0.15, y: y+0.25, w: w-0.3, h: 0.6,
  fontSize: 13, bold: true, color: '999999', fontFace: 'Arial',
  lineSpacingMultiple: 1.3
});
slide.addText('尚未觸及', {
  x: x+0.15, y: y+0.9, w: w-0.3, h: h-1.0,
  fontSize: 11, color: 'AAAAAA', fontFace: 'Arial', valign: 'top'
});
```

### Card-G｜灰底卡（次要資訊，補充說明）

```javascript
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: 'EEEEEE' },
  line: { color: 'EEEEEE', width: 0 }
});
// 標題
slide.addText('現有系統較難承接的', {
  x: x+0.2, y: y+0.2, w: w-0.4, h: 0.28,
  fontSize: 13, bold: false, color: '555555', fontFace: 'Arial'
});
// 內文
slide.addText('？為什麼這樣談\n？為什麼那時調價', {
  x: x+0.2, y: y+0.55, w: w-0.4, h: h-0.65,
  fontSize: 11, color: '888888', fontFace: 'Arial', valign: 'top',
  lineSpacingMultiple: 1.6
});
```

### Card-B｜黑底卡（核心強調，最重要結論）

```javascript
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: '1A1A1A' },
  line: { color: '1A1A1A', width: 0 }
});
// 強調符號 + 文字（白色）
slide.addText('★ 目前位置：L 社現況', {
  x: x+0.15, y, w: w-0.3, h,
  fontSize: 14, bold: true, color: 'FFFFFF', fontFace: 'Arial',
  align: 'center', valign: 'middle'
});
```

### Card-L｜左豎線卡（左邊粗線強調，重要段落）

```javascript
// 白底（或淺灰底）
slide.addShape(pres.shapes.RECTANGLE, {
  x, y, w, h,
  fill: { color: 'F5F5F5' },
  line: { color: 'F5F5F5', width: 0 }
});
// 左側粗豎線（4px，黑）
slide.addShape(pres.shapes.RECTANGLE, {
  x, y: y+0.05, w: 0.05, h: h-0.1,
  fill: { color: '1A1A1A' },
  line: { color: '1A1A1A', width: 0 }
});
// 文字（縮排）
slide.addText('核心代價：關鍵知識無法累積', {
  x: x+0.2, y: y+0.15, w: w-0.3, h: 0.3,
  fontSize: 13, bold: true, color: '1A1A1A', fontFace: 'Arial'
});
slide.addText('內文段落...', {
  x: x+0.2, y: y+0.5, w: w-0.3, h: h-0.6,
  fontSize: 12, color: '555555', fontFace: 'Arial', valign: 'top',
  lineSpacingMultiple: 1.4
});
```

---

## 底部金句元件（每頁收尾）

底部金句是此模板的靈魂元素，分三種形式：

### 形式A：規則線 + 金句（最常用）

```javascript
// 分隔線
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 5.0, w: 9.2, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});
// 金句文字
slide.addText('從觀察出發，改善方向可能不在新增系統，而在補齊現行系統未能銜接的部分', {
  x: 0.4, y: 5.02, w: 9.2, h: 0.3,
  fontSize: 11, color: '555555', fontFace: 'Arial', italic: false,
  lineSpacingMultiple: 1.3
});
```

### 形式B：左豎線框金句（強調版）

```javascript
// 淺灰底框
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 4.95, w: 9.2, h: 0.38,
  fill: { color: 'F5F5F5' },
  line: { color: 'F5F5F5', width: 0 }
});
// 左豎線
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 4.97, w: 0.045, h: 0.34,
  fill: { color: '1A1A1A' },
  line: { color: '1A1A1A', width: 0 }
});
// 金句
slide.addText('紙本成為管理用來補齊風險的方式。', {
  x: 0.55, y: 4.97, w: 8.95, h: 0.34,
  fontSize: 12, bold: true, color: '1A1A1A', fontFace: 'Arial',
  valign: 'middle'
});
```

### 形式C：純粗黑文字金句（最強調）

```javascript
slide.addText('報告完畢，謝謝聆聽', {
  x: 0.4, y: 5.1, w: 9.2, h: 0.3,
  fontSize: 16, bold: true, color: '1A1A1A', fontFace: 'Arial Black',
  align: 'center', valign: 'middle'
});
```

---

## 常用版面配置

### Layout-L：左文右圖/右卡（60/40）

```
┌─ 標題 ─────────────────────────────────────────────────────────────┐
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│  [左側內容 60%]              [右側卡片或圖片 40%]                   │
│  - 段落、要點、說明           Card-S / Card-G / 圖                  │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│ 底部金句                                                            │
└───────────────────────────────────────────────────────────────────┘
```

```javascript
const LEFT_X = 0.4, LEFT_W = 5.2, RIGHT_X = 5.9, RIGHT_W = 3.7;
const CONTENT_Y = 1.1, CONTENT_H = 3.7;
```

### Layout-2C：兩欄等分（各 50%）

```javascript
const COL1_X = 0.4, COL2_X = 5.1, COL_W = 4.6, CONTENT_Y = 1.1, CONTENT_H = 3.7;
```

### Layout-3C：三欄（卡片式方法/步驟）

```javascript
const COL_W = 2.8, COL_GAP = 0.2;
const COL1_X = 0.4, COL2_X = 3.4, COL3_X = 6.4;
const CONTENT_Y = 1.3, CONTENT_H = 3.5;
```

### Layout-3STAGE：三階段橫向（帶箭頭）

```javascript
// 三個等寬 Card，中間加箭頭符號
// → 用於「三段式發展歷程」如 Digitization → Digitalization → Digital Transformation
const STAGE_W = 2.7, STAGE_H = 3.0;
const STAGE1_X = 0.4, STAGE2_X = 3.5, STAGE3_X = 6.6;
const STAGE_Y = 1.3;

// 箭頭（→）
['→', '→'].forEach((arr, i) => {
  slide.addText(arr, {
    x: 3.3 + i * 3.1, y: STAGE_Y + STAGE_H/2 - 0.2, w: 0.3, h: 0.4,
    fontSize: 16, color: 'AAAAAA', fontFace: 'Arial', align: 'center'
  });
});
```

### Layout-FLOW：橫向流程箭頭（重點整理頁）

```javascript
// 適合「研究流程」「方法步驟」等橫向推進結構
const steps = ['概念型定義', '操作型定義', '問卷設計', '信度驗證', '線性迴歸分析'];
const BOX_W = 1.6, BOX_H = 0.38, BOX_Y = 1.5;
steps.forEach((step, i) => {
  const x = 0.4 + i * (BOX_W + 0.25);
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y: BOX_Y, w: BOX_W, h: BOX_H,
    fill: { color: i === currentStep ? '1A1A1A' : 'EEEEEE' },
    line: { color: i === currentStep ? '1A1A1A' : 'CCCCCC', width: 1 }
  });
  slide.addText(step, {
    x, y: BOX_Y, w: BOX_W, h: BOX_H,
    fontSize: 11, bold: i === currentStep,
    color: i === currentStep ? 'FFFFFF' : '555555',
    fontFace: 'Arial', align: 'center', valign: 'middle'
  });
  if (i < steps.length - 1) {
    slide.addText('→', {
      x: x + BOX_W + 0.02, y: BOX_Y, w: 0.22, h: BOX_H,
      fontSize: 13, color: 'AAAAAA', align: 'center', valign: 'middle'
    });
  }
});
```

### Layout-NUM：大數字編號清單（管理建議/改善方向）

```javascript
// 01/02/03 大數字 + 類別標籤 + 標題 + 內文
const items = [
  { num: '01', cat: '管理層面', title: '重新檢討「資料怎麼存、怎麼找」', body: '說明...' },
  { num: '02', cat: '工具應用', title: '是否需要一個「介於人與系統之間」的地方', body: '說明...' },
  { num: '03', cat: '衍接未來', title: '如果資料被整理起來，未來能做什麼', body: '說明...' },
];
items.forEach((item, i) => {
  const y = 1.2 + i * 1.2;
  // 大號碼
  slide.addText(item.num, {
    x: 0.4, y, w: 0.8, h: 0.5,
    fontSize: 32, bold: true, color: 'DDDDDD', fontFace: 'Arial Black'
  });
  // 類別標籤（號碼下方）
  slide.addText(item.cat, {
    x: 0.4, y: y+0.5, w: 0.8, h: 0.2,
    fontSize: 9, color: '888888', fontFace: 'Arial', align: 'center'
  });
  // 標題
  slide.addText(item.title, {
    x: 1.3, y: y+0.05, w: 8.3, h: 0.35,
    fontSize: 14, bold: true, color: '1A1A1A', fontFace: 'Arial'
  });
  // 內文
  slide.addText(item.body, {
    x: 1.3, y: y+0.42, w: 8.3, h: 0.72,
    fontSize: 11, color: '555555', fontFace: 'Arial',
    valign: 'top', lineSpacingMultiple: 1.35
  });
  // 細分隔線（非最後一項）
  if (i < items.length - 1) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 1.3, y: y + 1.16, w: 8.3, h: 0.008,
      fill: { color: 'EEEEEE' }, line: { color: 'EEEEEE', width: 0 }
    });
  }
});
```

### Layout-TABLE：黑白表格（麥肯錫風格）

```javascript
// 黑色 header + 白色交替行
slide.addTable(rows, {
  x: 0.4, y: 1.3, w: 9.2,
  rowH: 0.42,
  colW: [1.8, 4.5, 2.9],  // 依內容調整
  fontFace: 'Arial',
  border: { type: 'solid', color: 'DDDDDD', pt: 0.5 },
  fill: 'FFFFFF',
  // header row 個別設定
});
// Header 覆蓋（黑底白字）
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 1.3, w: 9.2, h: 0.42,
  fill: { color: '1A1A1A' }, line: { color: '1A1A1A', width: 0 }
});
['構面', '概念型定義', '操作型定義（問卷題數）'].forEach((h, i) => {
  const xs = [0.4, 2.2, 6.7], ws = [1.8, 4.5, 2.9];
  slide.addText(h, {
    x: xs[i]+0.1, y: 1.35, w: ws[i]-0.1, h: 0.32,
    fontSize: 12, bold: true, color: 'FFFFFF', fontFace: 'Arial', valign: 'middle'
  });
});
```

---

## Icon 卡片（3欄方法說明頁）

```javascript
// Icon 框（正方形，黑底白符號）
slide.addShape(pres.shapes.RECTANGLE, {
  x: x+0.15, y: y+0.15, w: 0.5, h: 0.5,
  fill: { color: '1A1A1A' }, line: { color: '1A1A1A', width: 0 }
});
slide.addText('●', { // 替換為實際圖示符號
  x: x+0.15, y: y+0.15, w: 0.5, h: 0.5,
  fontSize: 18, color: 'FFFFFF', align: 'center', valign: 'middle'
});
// 卡片標題
slide.addText('現場作業觀察', {
  x: x+0.15, y: y+0.72, w: w-0.3, h: 0.3,
  fontSize: 13, bold: true, color: '1A1A1A', fontFace: 'Arial'
});
// 內文
slide.addText('說明文字...', {
  x: x+0.15, y: y+1.05, w: w-0.3, h: h-1.15,
  fontSize: 11, color: '555555', fontFace: 'Arial', valign: 'top',
  lineSpacingMultiple: 1.35
});
```

---

## 結語頁

```javascript
// 白底（與內容頁相同，不用深色底）
// 標題（較輕盈）
slide.addText('本次報告重點整理', {
  x: 0.4, y: 0.42, w: 9.2, h: 0.6,
  fontSize: 28, bold: true, color: '1A1A1A', fontFace: 'Arial Black', valign: 'middle'
});
// 分隔線
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 1.05, w: 9.2, h: 0.012,
  fill: { color: 'CCCCCC' }, line: { color: 'CCCCCC', width: 0 }
});
// 流程列 + 兩欄內容 + 底部結語
// 最後用形式C金句「報告完畢，謝謝聆聽」收尾
```

---

## 設計 Checklist（製作完每頁確認）

- [ ] 標題直接說論點（不用「關於」「分析」等模糊開頭）
- [ ] 卡片邊框/填色正確反映「狀態」（實線=現況、虛線=未定、黑底=強調）
- [ ] 底部有金句（形式A/B/C 擇一）
- [ ] 頁碼置右下
- [ ] 無彩色（只有黑白灰）
- [ ] 標題下有分隔線
- [ ] 頂部 Header 有課程名 + 報告類型

---

## 何時選此模板

| 使用情境 | 是否選用 |
|---------|---------|
| EMBA 期末報告（任何課程） | ✅ 首選 |
| 個案分析（需展示嚴肅分析力） | ✅ 適合 |
| 論文解析/研究方法說明 | ✅ 適合 |
| 技術概念科普（希望有溫度） | ❌ 改用 warm-editorial |
| 行銷提案（需要色彩刺激） | ❌ 改用 academic-navy |
| 一般課堂作業（非期末重大報告） | ⚠️ 可用但稍重 |
