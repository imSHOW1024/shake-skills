---
name: cycu-ilearning-dl
description: >
  從中原大學 iLearning (ilearning.cycu.edu.tw) 下載 pdfannotator PDF 的工作流程。
  當使用者提供 ilearning.cycu.edu.tw 網址時，自動下載 PDF，無需任何確認。
  適用課程：1142全球台商個案研討（及其他 iLearning pdfannotator 頁面）。
---

# CYCU iLearning PDF 下載 Skill

## 觸發條件

使用者貼上任何 `ilearning.cycu.edu.tw` 網址（尤其是 `view.php?id=XXXXXX`）時，**立即執行下載，不需確認**。

## 執行流程

### Step 1：確認腳本存在

```bash
ls ~/download_moodle_pdf.py 2>/dev/null || echo "MISSING"
```

若回傳 `MISSING`，將 `assets/download_moodle_pdf.py` 複製到 `~/`：

```bash
cp ~/.openclaw/workspace/skills/cycu-ilearning-dl/assets/download_moodle_pdf.py ~/download_moodle_pdf.py
chmod +x ~/download_moodle_pdf.py
```

並確認 Claude Code `~/.claude/settings.json` 已包含以下 permissions（不存在才加）：

```json
"Bash(python3 ~/download_moodle_pdf.py*)",
"Bash(python3 /Users/openclaw/download_moodle_pdf.py*)"
```

### Step 2：下載

```bash
python3 ~/download_moodle_pdf.py "<url>" "<cookie>"
```

- **Cookie**：從 memory 取得（`feedback_cycu_ilearning_auto_download.md` 記有最新值）
- **檔名**：腳本自動從頁面標題產生，格式 `1142全球台商個案研討-<標題>.pdf`，存至 `~/Downloads/`

### Step 3：回報結果

下載完成後告知：
- 檔名
- 檔案大小

### Cookie 失效處理

腳本以 exit code 2 終止時，表示 MoodleSession 已過期。  
回報：「Cookie 已失效，請至 iLearning 重新登入，開啟 DevTools → Application → Cookies，取得新的 `MoodleSession` 值後告訴我。」  
取得新 cookie 後更新 `feedback_cycu_ilearning_auto_download.md`。

## 新裝置初次設定

在新裝置（如 14" MBP M5 Max）初次使用時，按 Step 1 操作後還需：

```bash
pip3 install requests --break-system-packages
```

## 備忘

- 課程名稱前綴：`1142全球台商個案研討`
- URL 規律：`https://ilearning.cycu.edu.tw/mod/pdfannotator/view.php?id=XXXXXX`
- PDF 藏在頁面 JavaScript 的 JSON-escaped URL（`\/` 跳脫）中
