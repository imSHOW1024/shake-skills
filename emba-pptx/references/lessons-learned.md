# 製作經驗累積

---

## v1.0｜2026-04｜企業危機管理期中報告

### 基本資訊
- **課程**：企業危機管理（鄭詠隆）
- **作業類型**：期中報告，個人口頭報告
- **頁數**：7 頁（封面 + 5 內容頁 + 結語）
- **製作工具**：pptxgenjs + matplotlib（Python 3.12）

### 工具組合
- `pptxgenjs`：PPTX 主體製作
- `matplotlib` + Python 3.12 venv：四象限圖 PNG 產出
- `pptx` skill（pptxgenjs.md）：語法參考
- LibreOffice `soffice` + `pdftoppm`：視覺 QA 轉圖
- subagent：逐頁視覺審查

### 成功做法

**設計層面：**
- 卡片式設計（A/B/C 三型）比純文字頁面視覺效果顯著提升
- Sandwich 深淺交替結構（封面深/內容淺/結語深）建立視覺節奏
- 三欄色塊（預防藍/控制橘/修復灰）直觀呈現三階段框架
- C型引用框搭配老師金句，強化課程連結感

**流程層面：**
- 圖片 Placeholder 策略讓 PPTX 結構製作與圖片生成解耦，穩定性更高
- matplotlib 精確座標控制四象限圖，比 AI 生成圖更可靠
- 建立 Python 3.12 venv 固化環境，與系統 python3 完全隔離
- `run.sh` 一鍵執行腳本，自動驗證環境 → 產圖 → 產 PPTX

**QA 層面：**
- 兩輪 subagent 視覺審查，第一輪找出 4 個嚴重問題後修復再驗
- 分離嚴重/中等/輕微問題分級處理，效率更高

### 待改善項目

**技術層面：**
- 中文字型（PingFang HK）在 matplotlib 中需明確指定，否則使用 DejaVu Sans 導致亂碼
- pptxgenjs 的 `ROUNDED_RECTANGLE` + 頂部矩形色條會露出圓角縫隙，須改用 `RECTANGLE`
- `shadow` 物件不可跨多個 `addShape` 重用（pptxgenjs 會 mutate in-place），需用 factory function

**設計層面：**
- Slide 2 頁面標題若過長，縮窄後會換行——標題文字本身也要精簡
- 右側小卡片與左側大圖表的間距需預留至少 0.3"，否則視覺擁擠

### 給下次的提醒

1. **頁數控制**：3.5 分鐘快語速 ≈ 7 頁上限，超過要精簡
2. **框架優先**：老師評分重點是框架應用正確性 > 視覺美觀度
3. **先問清楚**：報告時長、是否限制頁數、評分標準，再決定內容深度
4. **框架驗證**：製作前對照 `frameworks.md`，不要用錯框架
5. **Python 環境**：每個專案用獨立 venv，固定版本，附 `requirements.txt`
6. **QA 不省略**：至少一輪視覺審查，第一次 render 幾乎都有問題

---

*每次製作完成後，在此追加新版本記錄。*
