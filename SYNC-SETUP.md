# Shake Skills 同步方案說明

> 本文件說明目前實際採用的 sync 作法：GitHub repo + Windows Junction，讓 Cursor / Antigravity / OpenClaw 的 skills 目錄指向同一份 repo，改一處即同步。

---

## 一、設計原則

- **不依賴第三方同步軟體**：只用 Git + 作業系統的 Junction（目錄連結）。
- **單一真相來源**：skills 內容以 repo 為準；`git pull` 後即生效，無需複製或重裝。
- **路徑動態化**：所有指令使用 `$env:USERPROFILE`（或 `%USERPROFILE%`），同一份步驟適用不同 Windows 帳號與機器。
- **安全分段**：破壞性操作（刪除原始目錄、建立 Junction）獨立成「Prompt B」，與「只複製與備份」的 Prompt A 分開，避免一次誤跑到底。

---

## 二、整體架構

```
GitHub Repo（shake-skills）
         ↕ git pull / push
  本機 clone
  C:\HomeVibeCoding\shake-skills\
         │
         ├── ide-skills/          ← 所有 IDE 用 skill（Cursor + Antigravity 共用）
         └── openclaw-skills/     ← OpenClaw 用 skill + manifest.yml
                    │
                    │  Windows Junction（一次性設定）
                    ▼
  ┌─────────────────────────────────────────────────────────┐
  │  %USERPROFILE%\.cursor\skills-cursor       → ide-skills   │
  │  %USERPROFILE%\.gemini\antigravity\skills  → ide-skills   │
  │  %USERPROFILE%\.openclaw\skills            → openclaw-skills │
  └─────────────────────────────────────────────────────────┘
```

- **Cursor** 與 **Antigravity** 共用同一目錄 `ide-skills`，改一次兩邊都更新。
- **OpenClaw** 可選擇：
  - **Junction 到 openclaw-skills**（目前 ROG 上的作法）：repo 內放自訂/修改過的 skill，與 manifest 一起版控。
  - **僅用 manifest**：不建 junction，新機依 `openclaw-skills/manifest.yml` 用 `clawhub install <slug>` 安裝，repo 只放 manifest 與自訂 skill 的副本。

---

## 三、Repo 目錄結構

```
C:\HomeVibeCoding\shake-skills\
├── ide-skills/                  ← Cursor + Antigravity 共用（Junction 目標）
│   ├── docx/
│   ├── pdf/
│   ├── xlsx/
│   ├── pptx/
│   ├── frontend-design/
│   ├── brand-guidelines/
│   ├── doc-coauthoring/
│   ├── internal-comms/
│   ├── skill-creator/
│   ├── create-rule/
│   ├── create-skill/
│   ├── update-cursor-settings/
│   ├── skill-installer/
│   ├── webapp-testing/
│   ├── mcp-builder/
│   ├── canvas-design/
│   ├── algorithmic-art/
│   ├── theme-factory/
│   ├── web-artifacts-builder/
│   └── slack-gif-creator/
│
├── openclaw-skills/             ← OpenClaw Junction 目標（可選）
│   ├── manifest.yml            ← clawhub 安裝清單
│   ├── docx/
│   ├── pdf/
│   └── ...（僅放自訂/修改過的 skill）
│
├── .gitignore
└── SYNC-SETUP.md                ← 本說明
```

---

## 四、路徑對照（Windows）

| 工具 | 原始目錄（備份後會被刪除並改為 Junction） | Junction 指向 |
|------|------------------------------------------|----------------|
| Cursor | `%USERPROFILE%\.cursor\skills-cursor` | `C:\HomeVibeCoding\shake-skills\ide-skills` |
| Antigravity | `%USERPROFILE%\.gemini\antigravity\skills` | `C:\HomeVibeCoding\shake-skills\ide-skills` |
| OpenClaw | `%USERPROFILE%\.openclaw\skills` | `C:\HomeVibeCoding\shake-skills\openclaw-skills` |

Repo 路徑固定為 `C:\HomeVibeCoding\shake-skills`；使用者目錄一律用 `%USERPROFILE%`，換機器/帳號不必改指令。

---

## 五、初始化流程（第一次在這台機器設定）

### 前置：環境需求

- Node、Git 已安裝。
- 以下路徑存在（或之後會建立）：
  - `C:\HomeVibeCoding`
  - `C:\HomeVibeCoding\SpectroAnalyticsPlatform\.cursor\skills`（或你現有 skills 的來源）
  - `%USERPROFILE%\.cursor\skills-cursor`
  - `%USERPROFILE%\.gemini\antigravity\skills`
  - `%USERPROFILE%\.openclaw\skills`（OpenClaw 可選，沒有則 Step 7 會建立父目錄）

### Prompt A（安全階段：只複製 + 備份，不刪除、不建 Junction）

1. **步驟 0：環境確認**  
   執行 node -v、git --version、檢查上述路徑是否存在，全部回報後停下來等確認。

2. **步驟 1：Clone repo + 建立目錄**  
   - `cd C:\HomeVibeCoding`  
   - `git clone https://github.com/imSHOW1024/shake-skills.git`  
   - 在 `shake-skills` 下建立 `ide-skills`、`openclaw-skills`，回報目錄清單後停下來。

3. **步驟 2：複製現有 skills 到 repo（不刪任何原始目錄）**  
   - **2a 共用類**（docx, pdf, xlsx, pptx, frontend-design, brand-guidelines, doc-coauthoring, internal-comms）→ 複製到 `ide-skills` 與 `openclaw-skills` 各一份。  
   - **2b IDE 專用類**（skill-creator, webapp-testing, mcp-builder, canvas-design, algorithmic-art, theme-factory, web-artifacts-builder, slack-gif-creator）→ 僅複製到 `ide-skills`。  
   - **2c Cursor 全域**（create-rule, create-skill, update-cursor-settings）從 `%USERPROFILE%\.cursor\skills-cursor` 複製到 `ide-skills`。  
   - **2d Codex**：從 `%USERPROFILE%\.codex\skills\.system\skill-installer` 複製到 `ide-skills\skill-installer`。  
   - **2e** 在 `openclaw-skills` 建立 `manifest.yml`（記錄 clawhub 要安裝的 slug 清單）。  
   複製完成後列出 `ide-skills`、`openclaw-skills` 內容，回報後停下來。

4. **步驟 3：建立 .gitignore**  
   在 repo 根目錄建立 `.gitignore`（排除 node_modules、.env、*.zip、cache 等），回報後停下來。

5. **步驟 4：備份原始目錄**  
   - 將 `%USERPROFILE%\.cursor\skills-cursor` 壓縮為 `%USERPROFILE%\skills-backup-cursor-YYYYMMDD.zip`。  
   - 將 `%USERPROFILE%\.gemini\antigravity\skills` 壓縮為 `%USERPROFILE%\skills-backup-antigravity-YYYYMMDD.zip`。  
   回報兩個 zip 的檔名與大小後**停下來**，不要繼續做刪除或 Junction。

（可選）備份後做 30 秒抽查：解壓兩個 zip 到暫存目錄，確認裡面有 create-rule、create-skill、update-cursor-settings 及 Antigravity 的 skills 樹，再進行 Prompt B。

### Prompt B（刪除原始目錄 + 建立 Junction）

6. **步驟 5：Pre-flight**  
   確認以下路徑存在：  
   `C:\HomeVibeCoding\shake-skills`、`ide-skills`、`openclaw-skills`。缺一則中止。

7. **步驟 6–7：建立 Junction**  
   - 若目標已存在且為一般資料夾（非 Junction/symlink），先 `Remove-Item -Recurse -Force`。  
   - 若目標已是 reparse point（Junction），則略過。  
   - 建立目錄連結：  
     - `mklink /J "%USERPROFILE%\.cursor\skills-cursor" "C:\HomeVibeCoding\shake-skills\ide-skills"`  
     - `mklink /J "%USERPROFILE%\.gemini\antigravity\skills" "C:\HomeVibeCoding\shake-skills\ide-skills"`  
     - `mklink /J "%USERPROFILE%\.openclaw\skills" "C:\HomeVibeCoding\shake-skills\openclaw-skills"`（若採用 OpenClaw Junction）。  
   失敗時（例如權限不足）：以**系統管理員**重新開 PowerShell 再試；若公司政策禁止 mklink，改用手動複製到各目標路徑，不建 Junction。

8. **步驟 8：驗證**  
   用 `dir` 檢查上述三個目標路徑，確認列出的是 repo 內的 skill 目錄（如 docx、create-rule、manifest.yml 等）。

完成後，開啟 Cursor / Antigravity（及 OpenClaw）確認 skills 有被偵測。

---

## 六、日常工作流程

### 在這台機器上修改或新增 skill

- 直接編輯 `C:\HomeVibeCoding\shake-skills\ide-skills\` 或 `openclaw-skills\` 內對應的 skill。  
- 因為是 Junction，Cursor / Antigravity / OpenClaw 會即時看到變更。  
- 改完記得：

```powershell
cd C:\HomeVibeCoding\shake-skills
git add .
git commit -m "update: [skill名稱] [簡短說明]"
git push
```

### 換到另一台已設定 Junction 的裝置

```powershell
cd C:\HomeVibeCoding\shake-skills
git pull
```

Junction 已指向 repo，pull 後即生效，不需再複製或重裝。

### 新裝置第一次使用 OpenClaw（若未 Junction）

- 看 `openclaw-skills/manifest.yml` 的 slug 清單。  
- 在新機上執行：`clawhub install <slug>` 逐一安裝。  
- 自訂或修改過的 skill 可從 repo 的 `openclaw-skills/` 複製到該機的 `%USERPROFILE%\.openclaw\skills`。

---

## 七、.gitignore 要點

Repo 內應忽略：  
OS 垃圾檔、`node_modules`、Python 虛擬環境與 cache、`.env` 與金鑰、logs、IDE cache、以及本機備份用的 `*.zip`。  
具體內容見 repo 根目錄的 `.gitignore`。

---

## 八、還原方式（若日後要取消 Junction）

1. 刪除 Junction（不要用 `Remove-Item -Recurse`，否則會刪到 repo 內容）：  
   - `cmd /c rmdir "%USERPROFILE%\.cursor\skills-cursor"`  
   - 同理 `rmdir` 另外兩個目標。  
2. 從備份 zip 解壓回 `%USERPROFILE%\.cursor\skills-cursor` 與 `%USERPROFILE%\.gemini\antigravity\skills`。  
3. 之後改 skill 就改回各工具原本的目錄，不再透過 repo。

---

## 九、第二台裝置（Surface Pro）

G35CA 已完成同步後，在 **Surface Pro** 上第一次設定請用專用說明檔：

- **檔案**：repo 內 `SETUP-SURFACE-PRO.md`
- **用法**：在 Surface Pro 上先 clone repo 到 `C:\HomeVibeCoding\shake-skills`，用 Cursor 開啟該資料夾，打開 `SETUP-SURFACE-PRO.md`，依序把各步驟的「給 Agent 的指令」貼到 Cursor Agent 執行。

流程摘要：**前置 clone → 步驟 0 路徑檢查 → 步驟 1 補齊 repo/目錄（若需要）→ 步驟 2 第一次備份 → 步驟 3 建 Junction → 步驟 4 驗證**；之後日常在 Surface Pro 上執行 `git pull` 即可同步。

---

## 十、摘要

| 項目 | 說明 |
|------|------|
| Repo 位置 | `C:\HomeVibeCoding\shake-skills` |
| Cursor skills | Junction → `ide-skills` |
| Antigravity skills | Junction → `ide-skills` |
| OpenClaw skills | Junction → `openclaw-skills`（可選；或僅用 manifest + 手動安裝） |
| 備份 | Prompt A 步驟 4 產生 `skills-backup-cursor-YYYYMMDD.zip`、`skills-backup-antigravity-YYYYMMDD.zip` |
| 日常同步 | 改 repo 後 `git push`；他機 `git pull` 即同步 |
| Surface Pro 首次設定 | 見 repo 內 `SETUP-SURFACE-PRO.md`，在 Cursor 開啟後依步驟貼給 Agent 執行 |

*文件對應實際執行之 Prompt A（安全階段）與 Prompt B（刪除 + Junction），路徑以 ROG G35CA 使用之 `C:\HomeVibeCoding\shake-skills` 為準。*
