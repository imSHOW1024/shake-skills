# Lecture-Transcribe v3

## 架構

```
Telegram 音訊 → 類型判斷 → 轉錄(mlx→whisperx→cli)
→ Diarization → Speaker校正 → 規模判斷
→ LLM摘要(模板A/B/C/D) → Notion(雙DB)
```

## 檔案

| 檔案 | 用途 |
|------|------|
| lecture_pipeline.py | 主流程+Telegram互動 |
| transcribe.py | 轉錄引擎+diarization+切割合併 |
| prompts.py | LLM摘要模板A/B/C/D |
| notion_upload.py | 雙DB上傳+toggle heading |
| course_schedule.py | 課表推斷 |
| course_schedule.yaml | 課表資料 |

## EMBA 模板路由（含混搭）

- `D1`：理論 / 教授講授型
- `D2`：個案 / 討論 / 決策判斷型
- `D3`：行政 / 參訪 / 任務說明型
- `D4`：**報告講評 + 行政/行程混搭型**

### 特記事項 / 摘要要求（高優先）

若使用者訊息中明確寫了：
- `特記事項`
- `特殊要求`
- `摘要要求`
- `補充要求`

則這些內容必須視為**高優先整理規則**，直接影響：
- 模板路由（例如 D 類混搭）
- 章節順序與章節保留/省略
- 語言規則（例如只保留中文、不要雙語）
- 還原程度（例如老師講評要低抽象、不要延伸加料）

### Runtime flags（派工 patch）

- `skip_notion_ai_transcript`
  - 用途：當 Notion 筆記裡含有 **Notion AI 產出的長逐字稿** 時，避免它直接蓋過錄音原始轉錄。
  - 行為：
    1. 預設仍以**錄音原始轉錄**為主。
    2. Notion AI 長逐字稿先降權為 **reference / 備援來源**，不直接併入主逐字稿。
    3. 只有當系統判定原始轉錄品質太差、語意斷裂或密度異常時，才啟用 Notion AI transcript fallback 做輔助校對。
  - 建議使用時機：
    - 使用者貼的是「手寫筆記 + Notion AI transcript」混合頁。
    - Notion AI transcript 很長，且內容多半只是原始逐字稿的重複展開。
    - 本次任務重點是摘要品質，不想讓 Notion AI transcript 把 prompt 撐爆或污染主脈絡。

派工時可直接寫在訊息裡，例如：

```text
flag: skip_notion_ai_transcript
```

或：

```text
flags: skip_notion_ai_transcript
```

### LLM 成本護欄（2026-04 固化）

預設目標：**長音檔 chunk 階段優先走低成本模型，避免靜默打到 Google/Gemini 付費額度。**

- chunk 預設模型：`minimax-portal/MiniMax-M2.7`
- chunk fallback 預設順序：
  1. `google-ai/gemma-4-31b-it`
  2. `openai-codex/gpt-5.4`
- final fallback 預設順序：`minimax-portal/MiniMax-M2.7`
- **Google/Gemini fallback 預設關閉**，只有明確開 env 才允許進鏈
- **Gemini direct fallback 預設關閉**，避免 OpenClaw routing miss 時偷偷改打 Google API

可選環境變數：

```bash
LECTURE_TRANSCRIBE_ALLOW_GOOGLE_CHUNK_FALLBACK=1
LECTURE_TRANSCRIBE_ALLOW_GOOGLE_FINAL_FALLBACK=1
LECTURE_TRANSCRIBE_ALLOW_GOOGLE_DIRECT_FALLBACK=1
```

規則：
- 沒開上述 env，就不應出現 Google/Gemini fallback
- 若實際用了 Google fallback，報告內應明確顯示 warning 與實際成功模型
- `regen_summary.py` 與主 pipeline 採同一套成本護欄策略

### Few-shot 範例

- `references/few-shot-d4-mixed.md`
  - 用途：D4（報告講評 + 行政/行程混搭）示範輸出
  - 規則：模仿**結構、章節順序、資訊密度、措辭控制**，不要照抄內容
  - 目前重點：儘量還原原意、不替講者補完因果、不自行延伸評論、不把簡報本體重講一遍
- `references/few-shot-d4-crossculture-lecture-heavy.md`
  - 用途：D4 第二示範，偏「講評較完整 + 行政資訊較重」
  - 規則：模仿**更完整的講評收斂方式**與**行程/費用/注意事項/待辦拆章節**，不要照抄內容
- 參考索引：`references/README.md`

### 作業路徑說明 / 免責聲明（全模板）

- `作業路徑說明` 已固化為**全模板共用 footer**，不限 EMBA 模板
- Notion 端最後一段免責聲明固定使用 **quote block** 呈現

## 雙 DB

| DB | 用途 |
|----|------|
| 課堂摘要庫 `f7fea4c1...` | EMBA |
| 商務會談摘要DB `158465ef...` | 商務 |

## ⚠️ 絕對規則：使用者筆記頁 ≠ 上傳目標

當使用者提供 Notion URL 作為「既有筆記參考」時：
- ✅ 讀取該頁面內容作為 LLM 輸入（既有筆記合併）
- ✅ 摘要結果 → 上傳到**課堂摘要 DB**（`upload_emba()`，新建頁面）
- ❌ 絕對不可以 `overwrite_page()` 覆蓋使用者的手寫筆記頁

只有當使用者明確說「更新/覆蓋這個頁面」時，才能 overwrite。
否則一律新建到對應 DB。

---

## Notion 安全護欄（dry-run / parent check）

### 核心概念

- **dry-run**：正式寫入前，先用唯讀方式預覽「會寫到哪個 DB / data source、標題會長怎樣、metadata 是否合理」
- **parent check**：若是 overwrite 既有 Notion 頁面，先確認該頁 `parent.database_id` 與 `parent.data_source_id` 是否真的屬於預期 DB；不符就拒絕覆蓋

### 這層護欄在防什麼

- 把課堂摘要誤寫到原始課堂筆記 DB
- 因 Notion 新版 `database + data_source` 結構而發生 silent misroute
- 用錯 page id 導致跨 DB 覆蓋
- schema 漂移後看似成功、實際落點錯誤

### 上傳前檢查清單

1. 確認這筆內容的 `type` / 路由（EMBA vs business）正確
2. 解析目標 `database_id` 與 `data_source_id`
3. 檢查 Notion schema 是否包含必要欄位（title / 日期 / 教授 / 摘要等）
4. 預覽這次寫入的 title 與 metadata
5. 若是 overwrite：先讀目標頁 parent；**不在預期 DB / data source 就拒絕**
6. 建頁後再回讀 parent；不符則直接報錯，不算成功

### 唯讀 dry-run 指令

```bash
python skills/lecture-transcribe/scripts/notion_dry_run.py \
  --db-type emba \
  --markdown "/Users/openclaw/Documents/小龍女知識庫/EMBA/02 每週課堂筆記/全球台商個案研討/2026-03-28_全球台商個案研討.md"
```

若要檢查某個既有 Notion 頁面能不能安全 overwrite，再加 `--page`：

```bash
python skills/lecture-transcribe/scripts/notion_dry_run.py \
  --db-type emba \
  --markdown "/path/to/note.md" \
  --page "https://www.notion.so/..."
```

輸出重點：
- `database_id`
- `data_source_id`
- `preview_title`
- `schema_fields`
- `page_parent_matches_expected`（overwrite 前最重要）

### 規則

- **預設優先新建到正確摘要 DB**，不要直接覆蓋使用者原筆記
- **所有 overwrite 都應傳 `expected_db_type`**；沒有 guard 就不該執行
- 若 dry-run 顯示 parent 不符、metadata 缺漏或 schema 不符，先停下來修，不要硬寫

## 模板

| 模板 | 條件 | 重點 |
|------|------|------|
| A小型 | ≤4人且<1hr | Q&A+Action |
| B中型 | 5-8人或1-2hr | 各方立場 |
| C大型 | >8人或>2hr | 主導者指示+分部門 |
| D課堂 | emba | 知識萃取+產業應用 |

## 設置

```bash
cd ~/shake-skills && git pull
cd openclaw-skills/lecture-transcribe
bash install_whisperx.sh
bash check_env.sh
bash test_whisperx.sh test.m4a
```

## 環境變數

```
NOTION_API_KEY=ntn_...   # 必須
HF_TOKEN=hf_...          # 選填(diarization)
```
