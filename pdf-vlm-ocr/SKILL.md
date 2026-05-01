# PDF VLM OCR Skill

用多模態視覺語言模型（VLM）做 PDF OCR，品質遠超傳統 OCR 引擎。

## 何時使用

- 掃描 PDF 需要轉成可讀文字
- 傳統 OCR（RapidOCR / PaddleOCR / Tesseract）品質不足
- 需要高品質繁體中文辨識

## 架構

```
掃描 PDF → PyMuPDF 轉每頁 PNG → Gemini VLM 逐頁辨識 → 合併文字
```

與傳統 OCR 的關鍵差異：VLM 同時具備視覺辨識 + 語言理解，能根據上下文自動校正相似字形（後/俊、嗎/媽 等），並正確分離正文、側邊欄、圖說。

## 使用方式

### 基本用法

```bash
cd /Users/openclaw/.openclaw/workspace
source skills/pdf-vlm-ocr/.venv/bin/activate
python skills/pdf-vlm-ocr/vlm_ocr.py input.pdf -o output.md
```

### 品質預設（推薦用法）

```bash
python vlm_ocr.py input.pdf -o output.md -q fast     # Flash/200dpi — 最快最省
python vlm_ocr.py input.pdf -o output.md -q normal   # Flash/250dpi — 預設，日常夠用
python vlm_ocr.py input.pdf -o output.md -q high     # Pro/300dpi — 最高品質
```

| 預設 | 模型 | DPI | 延遲 | 適用場景 |
|------|------|-----|------|----------|
| `fast` | Flash | 200 | 1s | 快速預覽、草稿 |
| `normal` | Flash | 250 | 1.5s | **日常使用（預設）** |
| `high` | Pro | 300 | 3s | 正式引用、複雜排版 |

### 完整參數（覆蓋預設）

```bash
python vlm_ocr.py input.pdf \
  -o output.md \
  -q high \                # 品質預設
  -m gemini-2.5-pro \      # 手動覆蓋模型
  --dpi 300 \              # 手動覆蓋 DPI
  --pages 1-10 \           # 頁碼範圍（預設全部）
  --delay 3                # 手動覆蓋延遲
```

### 分段跑（避免超時）

長 PDF（>30 頁）建議分段：

```bash
python vlm_ocr.py input.pdf -o p1.md --pages 1-25 --delay 2
python vlm_ocr.py input.pdf -o p2.md --pages 26-50 --delay 2
cat p1.md p2.md > combined.md
```

## 環境需求

- Python venv: `skills/pdf-vlm-ocr/.venv`
- 套件: PyMuPDF, Pillow, google-genai
- 環境變數: `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`

## 模型選擇建議

| 模型 | 速度 | 品質 | 成本 | 適用場景 |
|------|------|------|------|----------|
| gemini-2.5-flash | 快（~10s/頁） | 極佳 | 低 | **預設推薦** |
| gemini-2.5-pro | 慢（~20s/頁） | 頂級 | 中 | 品質要求極高時 |

## 後處理建議

VLM OCR 輸出後通常需要：

1. **去除頁碼**：`re.sub(r'\n\d{3}\n', '\n', text)`
2. **去除重複頁首/頁尾**：用 regex 移除書名、章節名等反覆出現的行
3. **加 frontmatter**：根據用途加 Obsidian / Notion 的 metadata
4. **合併分頁斷行**：VLM 可能在頁面邊界斷句

## 已知限制

- 純圖片封面頁可能回傳空白（正常行為）
- Gemini API 有 RPM 限流，長 PDF 需要設 delay
- 極模糊或手寫掃描仍可能有少量錯字
