# 📚 EMBA 課堂錄音 → Notion 自動化 Pipeline

## 架構圖

```
┌─────────────┐     ┌──────────────────────────────────────────────┐
│  Shawn 手機  │     │  小龍女 (MacBook Pro M1 MAX)                  │
│  錄音 → 傳送 │────▶│                                              │
│  Telegram    │     │  ┌─────────────┐                             │
└─────────────┘     │  │ OpenClaw     │                             │
                    │  │ Telegram Bot │                             │
                    │  └──────┬───────┘                             │
                    │         │ 下載音訊                             │
                    │         ▼                                     │
                    │  ┌─────────────────┐                          │
                    │  │ WhisperX        │ ~/whisperx-env           │
                    │  │ + large-v3      │ CPU int8                 │
                    │  │ + pyannote      │ HF_TOKEN                │
                    │  │   diarization   │                          │
                    │  └──────┬──────────┘                          │
                    │         │ segments + speakers                  │
                    │         ▼                                     │
                    │  ┌─────────────────┐    ┌──────────────────┐  │
                    │  │ 課表自動推斷     │◀───│ course_schedule  │  │
                    │  │ (日期→課程+教授) │    │ .yaml            │  │
                    │  └──────┬──────────┘    └──────────────────┘  │
                    │         │                                     │
                    │         ▼                                     │
                    │  ┌─────────────────┐                          │
                    │  │ Telegram 互動    │ ◀─── Shawn 確認/補充     │
                    │  │ 確認 metadata   │       關鍵字、備註       │
                    │  │ + 關鍵字補充    │                          │
                    │  └──────┬──────────┘                          │
                    │         │                                     │
                    │         ▼                                     │
                    │  ┌─────────────────┐     ┌──────────────────┐ │
                    │  │ Markdown 生成   │────▶│ 本地備份          │ │
                    │  │ + Speaker 標注  │     │ ~/whisperx-outputs│ │
                    │  └──────┬──────────┘     └──────────────────┘ │
                    │         │                                     │
                    │         ▼                                     │
                    │  ┌─────────────────┐                          │
                    │  │ Notion API      │ NOTION_TOKEN             │
                    │  │ 上傳課堂摘要庫  │                          │
                    │  └─────────────────┘                          │
                    └──────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │ Notion 課堂摘要庫              │
                    │ DB: f7fea4c1...               │
                    │                              │
                    │ ┌──────────────────────────┐  │
                    │ │ 企業研究方法 2026-03-07   │  │
                    │ │ 教授: 顧志遠              │  │
                    │ │ 關鍵字: 質性研究, 信效度  │  │
                    │ │ [完整逐字稿 + Speaker]    │  │
                    │ └──────────────────────────┘  │
                    └──────────────────────────────┘
```

## 設置清單

### Phase 1: WhisperX 環境 (今天做)

- [ ] 在小龍女執行 `install_whisperx.sh`
- [ ] 建立 HuggingFace token (Read 權限)
- [ ] Accept pyannote 兩個模型:
  - https://huggingface.co/pyannote/segmentation-3.0
  - https://huggingface.co/pyannote/speaker-diarization-3.1
- [ ] 設定 `~/.zshrc`:
  ```bash
  export HF_TOKEN="hf_..."
  ```
- [ ] 用 `test_whisperx.sh` 跑一段測試音訊，確認 diarization 正常

### Phase 2: Pipeline 整合

- [ ] 建立目錄: `~/openclaw-skills/lecture-transcribe/`
- [ ] 放入: `lecture_pipeline.py`, `course_schedule.yaml`, `skill.yaml`, `requirements.txt`
- [ ] 安裝額外依賴: `pip install notion-client pyyaml` (在 whisperx-env 裡)
- [ ] CLI 手動測試:
  ```bash
  source ~/whisperx-env/bin/activate
  python lecture_pipeline.py test_audio.mp3 2026-03-07 14:30
  ```
- [ ] 確認 Notion 頁面建立成功

### Phase 3: Notion DB 欄位對齊

- [ ] 確認 Notion 課堂摘要庫現有欄位名稱
- [ ] 對齊 `lecture_pipeline.py` 裡的 properties mapping
- [ ] 預期欄位:

| 欄位       | 類型          | 對應值                          |
|-----------|--------------|-------------------------------|
| 名稱       | Title        | "{課程名稱} {日期}"              |
| 日期       | Date         | 錄音日期                        |
| 教授       | Rich Text    | 教授姓名                        |
| 關鍵字     | Multi-select | 使用者補充的關鍵字               |
| 錄音長度   | Rich Text    | "1h 23m 45s"                   |
| 學期       | Select       | "114-2"                        |
| 狀態       | Status       | "已轉錄" / "待整理"             |

### Phase 4: OpenClaw Telegram 整合

- [ ] 在 OpenClaw 主框架加入音訊 handler
- [ ] 接 `handle_audio_message()` 的 `send_message` / `ask_user` callback
- [ ] 測試完整流程: Telegram 傳音訊 → 自動轉錄 → 確認 → Notion

### Phase 5: 優化 (日後)

- [ ] 加入 LLM 摘要 (用 MiniMax / Gemini Flash 生成重點整理)
- [ ] 自動提取關鍵字 (LLM-based)
- [ ] 週六多堂課連續錄音的自動切割
- [ ] Markdown → Notion block 格式進階處理 (表格、callout)
- [ ] shake-skills repo 同步此 skill

## 環境變數總覽

```bash
# ~/.zshrc 需加入:
export HF_TOKEN="hf_..."           # HuggingFace (diarization)
export NOTION_TOKEN="ntn_..."      # Notion API (OpenClaw 可能已設定)
```

## 快速指令

```bash
# 安裝
bash install_whisperx.sh

# 手動測試 WhisperX
bash test_whisperx.sh ~/Downloads/test.mp3

# 手動測試完整 pipeline (含 Notion 上傳)
source ~/whisperx-env/bin/activate
python lecture_pipeline.py recording.mp3 2026-03-08 09:30

# 確認 Notion DB schema
python -c "
from notion_client import Client
import os, json
c = Client(auth=os.environ['NOTION_TOKEN'])
db = c.databases.retrieve('f7fea4c19f1e4dd58e0da38dee21a2d8')
for k, v in db['properties'].items():
    print(f'{k}: {v[\"type\"]}')
"
```
