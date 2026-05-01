---
name: lme-monitor
description: Monitor LME Primary Aluminum pricing with the local lme-monitor project using OpenClaw browser profiles, Python scripts, SQLite, and cron. Use when asked to run or debug the LME daily pipeline, fetch latest LME Primary Aluminum cash prices, convert USD/ton to TWD/kg using Bank of Taiwan FX, inspect SQLite records, import historical XLSX data, backfill records, or maintain the recurring cron-based LME monitor workflow and summary format.
---

# LME Monitor

Project root: `/Users/openclaw/.openclaw/workspace/lme-monitor`

## Core rules

- Work inside project root.
- Use local virtualenv: `./.venv/bin/python`
- `--browser-profile` is kept only for legacy script compatibility. Current OpenClaw browser CLI no longer exposes a per-command browser-profile flag, so do not assume passing `openclaw` changes browser session behavior.
- Default DB: `./db/lme_monitor.db`
- Target metal: **AL_A00 / LME Primary Aluminum only** — never write or reference other metals.
- LME 直接 curl/requests 會被 Cloudflare 擋，用 browser-assisted flow。
- FX 來源：台灣銀行 HTML（`bot_html`）
- SMM 來源：`https://hq.smm.cn/h5/alu-price`（`__NEXT_DATA__` JSON，不需瀏覽器）
- 外部風險分析：呼叫 `generate_analysis.py`，讀取 `context/business_context.md` 作為背景，Claude Sonnet 4.6（OAuth token 自動從 `~/.openclaw/agents/main/agent/auth-profiles.json` 讀取）；分析只聚焦市場面、經濟面、匯率面、供需面、航運面、能源面與地緣政治面，不討論單一公司成本或客戶交涉處境
- **新聞引用（2026-04-01 起）**：delivery sub-agent 在生成分析前，先用 `web_fetch` 抓取 Reuters / Fastmarkets / Mining.com 等主流金屬媒體，提取鋁/基本金屬相關標題，注入 `build_analysis_prompt(payload, news_context=...)` 的 `news_context` 參數，引用時需標明來源（如「路透報導指出...」）；若抓取失敗則只基於數據分析
- **時間備註 footer（2026-04-01 起）**：`run_daily_pipeline.py` 會在摘要底部自動加上資料時間說明，說明台北抓取時間、LME 延遲發布原因（倫敦時差 7 小時），以及週末/假日間隔說明；邏輯在 `run_daily_pipeline.py` 的 timing_note 區塊，根據 `day_gap`（`end_date - as_of_date`）動態產生

---

## Standard commands

### Full daily pipeline + Discord delivery（正式 cron 路徑）

```bash
cd /Users/openclaw/.openclaw/workspace/lme-monitor && \
  ./.venv/bin/python scripts/run_daily_and_notify.py \
  --db ./db/lme_monitor.db \
  --browser-profile openclaw \
  --target channel:1483965286532120670
```

### Full daily pipeline（僅產生 JSON / 除錯用）

```bash
cd /Users/openclaw/.openclaw/workspace/lme-monitor && \
  ./.venv/bin/python scripts/run_daily_pipeline.py \
  --db ./db/lme_monitor.db \
  --browser-profile openclaw \
  --capture-chart
```

### Dry run（不寫 DB，但仍呼叫 LLM 分析）

```bash
cd /Users/openclaw/.openclaw/workspace/lme-monitor && \
  FORCE_ANALYSIS=1 ./.venv/bin/python scripts/run_daily_pipeline.py \
  --db ./db/lme_monitor.db \
  --browser-profile openclaw \
  --capture-chart --dry-run
```

### Inspect latest prices

```bash
sqlite3 /Users/openclaw/.openclaw/workspace/lme-monitor/db/lme_monitor.db \
  "select metal, as_of_date, cash_seller_usd, usd_twd, cash_seller_twd_per_kg, smm_avg_cny, smm_twd_per_kg from market_prices order by as_of_date desc limit 5;"
```

### Inspect latest summaries

```bash
sqlite3 /Users/openclaw/.openclaw/workspace/lme-monitor/db/lme_monitor.db \
  "select id, metal, as_of_date, model, is_anomaly, substr(summary_text,1,200) from market_summaries order by id desc limit 5;"
```

### Inspect latest metrics

```bash
sqlite3 /Users/openclaw/.openclaw/workspace/lme-monitor/db/lme_monitor.db \
  "select metal, as_of_date, cash_seller_change_usd, cash_seller_change_pct, lme_smm_spread_twd_per_kg, lme_smm_spread_pct, is_anomaly from market_metrics order by as_of_date desc limit 5;"
```

### Cron history

```bash
openclaw cron runs --id 9bed35b3-066e-45b3-8e0f-d7858d92d044 --limit 10
```

---

## Production cron

| 項目 | 值 |
|------|-----|
| Job name | `lme-daily-monitor` |
| Job id | `9bed35b3-066e-45b3-8e0f-d7858d92d044` |
| Schedule | `0 5 * * *` Asia/Taipei |
| sessionTarget | `isolated` |
| agent | `main` |
| model | `minimax-m2.5` |
| delivery | `none` |

### Cron 執行流程（每日 09:00）

> **注意（2026-04-02）：** cron 架構再次優化。舊架構 Orchestrator 在 pipeline 完成前就 spawn delivery sub-agent，導致 `ANALYSIS_PROMPT` 傳入空值，新聞引用與分析無法生成。

**架構：Orchestrator（純 spawn）+ Delivery Sub-agent（all-in-one）**

1. **cron trigger**（09:00 UTC+8）→ 啟動 isolated Orchestrator agent（MiniMax M2.7）
2. **Orchestrator**：立刻 `sessions_spawn` delivery sub-agent（model=claude-sonnet-4-6，runTimeoutSeconds=900），然後直接結束（不執行 pipeline，不等待任何命令）
3. **Delivery Sub-agent**（獨立 session，900s timeout，Claude Sonnet 4.6）：
   - `exec background:true` 啟動 `run_daily_pipeline.py`
   - `process(poll)` 輪詢等待完整 JSON 輸出（最多 15 輪 × 30s）
   - 解析 JSON，提取 `summary_row.summary_text`、`analysis_prompt`、`chart_capture.image_path` 等
   - **自救邏輯**：若 `skipped=true` 或 `analysis_prompt` 為空 → 從 DB 重建 payload，重新生成 `analysis_prompt`
   - 用 Brave Search API 抓最新鋁/LME 新聞（備援：Google News RSS）
   - 自行生成【外部風險分析】（150-250 字，含新聞引用，標明媒體來源）
   - 組合完整報告（summary_text + 分析）
   - Components v2 卡片格式發 Discord + 截圖
   - `send_line.py` 發 LINE（含截圖公開 URL）
   - 輸出完成行（→ cron announce 廣播）
4. **不呼叫 `run_daily_and_notify.py`**（subprocess SIGTERM 問題）

**關鍵設計原則**：pipeline 必須在 delivery sub-agent 內部同步等待完成，再提取資料，確保 `analysis_prompt` 不為空。

**LINE 雙軌發送**：Discord 文字+截圖同步發 LINE，確保 LINE 使用者收到與 Discord 相同內容。

---

## Summary format

商業新聞風格，適合直接轉貼公司群組。Pipeline 自動產出，**不要由 cron agent 重新生成或改寫**。

結構（依序）：
1. `## <鋁價市場日報>`
2. `### LME 市場`：交易日、Cash Seller (Offer) USD/噸、台銀匯率、TWD/kg、日波動
3. `### SMM 中國現貨`：交易日、A00 鋁（上海）CNY/MT、台銀 CNY/TWD、扣 13% 增值稅後 TWD/kg、日波動
4. `### 市場對照`：LME vs SMM 價差與波動提醒
5. `【外部風險分析】`（Claude Sonnet 4.6 產出，含新聞引用；delivery sub-agent 先抓 Reuters/Fastmarkets/Mining.com，再注入 analysis prompt）
6. `---` 分隔線 + `📌 資料說明`：自動產出，說明台北抓取時間、LME 延遲原因、週末/假日間隔

排版規則：
- 關鍵數據使用 `**粗體**`
- 保留空行與小標，提升 Discord 內可讀性
- 不使用 markdown 表格

SMM 換算：`smm_avg_cny / 1000 / 1.13 × cny_twd`

若摘要包含銅或任何非 AL_A00 金屬 → 視為無效，不得儲存或送出。

---

## Business context

背景文件：`context/business_context.md`（LLM prompt 固定引用）

核心觀察：
- 中東局勢與荷姆茲海峽風險會影響航運、能源與國際鋁供應預期
- LME 現貨 vs 3M 的 Backwardation / Contango 反映短線供需是否緊張
- LME vs SMM 的價差可觀察國際盤與中國盤誰主導市場情緒
- 美元、人民幣與全球景氣變化會改變台幣視角下的鋁價壓力

---

## Pipeline output fields

```
summary_row.summary_text       完整摘要（直接送出）
chart_capture.image_path       截圖絕對路徑
price.cash_seller_usd
price.cash_seller_twd_per_kg
price.smm_avg_cny
price.smm_twd_per_kg
metrics.lme_smm_spread_twd_per_kg
metrics.lme_smm_spread_pct
metrics.is_anomaly
metrics.anomaly_reason
```

---

## Latest report workflow

阿翔要求最新報告時：
1. 查 `market_summaries` 最新 AL_A00 row
2. 若 `summary_text` 包含 SMM 段落與【外部風險分析】→ 直接用
3. 若摘要過期或格式不符 → 重新執行 pipeline（含 `--capture-chart`）
4. 送文字後補送截圖

---

## Data model

Tables：`market_prices`（含 smm_*）、`fx_rates`、`market_metrics`（含 lme_smm_spread_*）、`market_summaries`（含 chart_image_path）、`imports`

---

## Delivery — Components v2 卡片格式

> **優化（2026-04-01）：** Discord 報告使用 Components v2 卡片格式呈現，LINE 發送相同文字內容。

### Discord 卡片格式（Components v2）

**正確語法（用 `--components` 參數）：**
```bash
openclaw message send \
  --channel discord \
  -t channel:1483965286532120670 \
  -m "📊 LME 鋁價市場日報" \
  --components '{
    "text": "📊 LME 鋁價市場日報 — YYYY-MM-DD",
    "container": {"accentColor": "#FFB800"},
    "blocks": [
      {"type": "text", "text": "### 🔵 LME 市場\\n<lme_text>"},
      {"type": "separator"},
      {"type": "text", "text": "### 🔶 SMM 中國現貨\\n<smm_text>"},
      {"type": "separator"},
      {"type": "text", "text": "### 📐 市場對照\\n<spread_text>"},
      {"type": "separator"},
      {"type": "text", "text": "【外部風險分析】\\n<analysis_text>"}
    ]
  }'
```

> ⚠️ **注意**：不要用 `--json '{"action":"send"...}'` 語法，那是錯的。正確用法是 `--components` 直接接 JSON。

截圖（單獨訊息，緊接在卡片後）：
```bash
openclaw message send \
  --channel discord \
  -t channel:1483965286532120670 \
  --message "📈 LME 鋁價圖（YYYY-MM-DD）" \
  --media <chart_capture.image_path>
```

### LINE（同步發送相同文字內容）
```bash
cd /Users/openclaw/.openclaw/workspace/lme-monitor && \
  ./.venv/bin/python send_line.py "<final summary>"
```

### 設計原則
- Accent color：`#FFB800`（鋁金色主題）
- 卡片抬頭：`📊 LME 鋁價市場日報`
- 四大區塊：LME 市場 → SMM 中國現貨 → 市場對照 → 外部風險分析
- `type: "separator"` 分隔各區塊
- 數據用 `**粗體**`，emoji 作為區塊識別符

截圖規格：Offer 紅線、預設一個月區間、Selector: `.openclaw-lme-capture-target`、輸出目錄: `artifacts/charts/`

---

## Cron maintenance

```bash
openclaw cron list
openclaw cron runs --id 9bed35b3-066e-45b3-8e0f-d7858d92d044 --limit 20
openclaw cron run  9bed35b3-066e-45b3-8e0f-d7858d92d044   # 手動觸發測試
```

規則：Orchestrator 角色只負責確認資料 + spawn delivery sub-agent；Delivery sub-agent 負責 MiniMax 分析 + Discord/LINE 發送。不要在 Orchestrator prompt 內直接呼叫 MiniMax 或嘗試組報告。

---

## Post-run checklist

1. `cron runs` → `status=ok`
2. `#cron-notify` 收到 cron announce 完成通知
3. `#cron-notify` 收到 delivery sub-agent 發出的摘要文字（含 SMM 段落 + 【外部風險分析】）
4. `#cron-notify` 收到截圖（在摘要後）
5. LINE 收到相同摘要文字
6. `market_prices` 最新 row：`smm_avg_cny` 不為 null
7. `market_metrics` 最新 row：`lme_smm_spread_twd_per_kg` 不為 null

---

## Debug checklist

| 症狀 | 排查 |
|------|------|
| Orchestrator 超時（>10s） | 檢查 sessions_spawn 是否成功；sub-agent 是否有啟動 |
| Delivery sub-agent 沒發 report | 檢查 sub-agent session 是否成功；MiniMax 是否 timeout |
| Discord 沒收到 | 確認 `openclaw message send` 有成功（檢查 session history） |
| LINE 沒收到 | 檢查 `send_line.py` exit code；LINE Bot 是否在有效期內 |
| MiniMax 分析空白 | 檢查 sub-agent 的 MiniMax API 回應；business_context.md 是否存在 |
| 截圖沒附上 | 確認 chart_image_path 存在且 sub-agent 有執行 --media 指令 |
| 截圖未附上 | 確認 chart_image_path 存在；delivery sub-agent 有執行 `--media` 指令 |
| 摘要文字未收到 | 確認 delivery sub-agent 的 `openclaw message send` 有成功；檢查 sub-agent session history |
| 分析/新聞引用缺失 | 99% 是 `analysis_prompt` 空值：Orchestrator 在 pipeline 完成前就 spawn sub-agent。修復：delivery sub-agent 需自己跑 pipeline + poll 等待完整 JSON，再提取 analysis_prompt |
| 自救流程：補發時 pipeline skipped | skipped=true 時從 DB `SELECT summary_payload_json FROM market_summaries ORDER BY id DESC LIMIT 1` 重建 payload，再呼叫 `generate_analysis.py --payload-json` 生成 prompt |
