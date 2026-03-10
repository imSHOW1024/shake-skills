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

## 雙 DB

| DB | 用途 |
|----|------|
| 課堂摘要庫 `f7fea4c1...` | EMBA |
| 商務會談摘要DB `158465ef...` | 商務 |

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
