# Surface Pro — Shake Skills 同步設定指南

> **使用時機**：在 Surface Pro 上**第一次**設定 skills 同步時使用。  
> **使用方式**：在 Surface Pro 開啟 Cursor，開啟本 repo（`C:\HomeVibeCoding\shake-skills`），打開本文件，依序把「給 Agent 的指令」貼到 **Cursor Agent** 執行；每步完成後可檢查輸出再繼續。

---

## 前置：若尚未 clone repo

在 Surface Pro 上**先做一次**（PowerShell 或 Cursor 終端機）：

```powershell
# 建立目錄（若不存在）
New-Item -ItemType Directory -Force -Path "C:\HomeVibeCoding"
cd C:\HomeVibeCoding

# Clone（若已存在可改為 cd shake-skills 後 git pull）
git clone https://github.com/imSHOW1024/shake-skills.git
```

完成後在 Cursor 用 **File → Open Folder** 開啟 `C:\HomeVibeCoding\shake-skills`，再打開本文件 `SETUP-SURFACE-PRO.md`。

---

## 步驟 0：環境與路徑檢查（不改任何檔案）

**請在 Cursor Agent 中貼上以下指令，執行後回報結果。**

```
在 Surface Pro 上執行 shake-skills 同步的「步驟 0：環境與路徑檢查」。

請在 PowerShell 依序執行並完整回報輸出：

$userHome = $env:USERPROFILE
node -v
git --version
Write-Host "USERPROFILE=$userHome"

$paths = @(
  "C:\HomeVibeCoding",
  "C:\HomeVibeCoding\shake-skills",
  "C:\HomeVibeCoding\shake-skills\ide-skills",
  "C:\HomeVibeCoding\shake-skills\openclaw-skills",
  "$userHome\.cursor",
  "$userHome\.cursor\skills-cursor",
  "$userHome\.gemini\antigravity",
  "$userHome\.gemini\antigravity\skills"
)
foreach ($p in $paths) { Write-Host "$p : $(Test-Path $p)" }

回報後停下來等我確認再繼續。
```

確認 repo、ide-skills、openclaw-skills 存在，以及 .cursor、.gemini\antigravity 路徑狀態（skills-cursor / skills 可能尚未存在，沒關係）。

---

## 步驟 1：取得 repo 並確認路徑（若尚未 clone / 目錄缺漏）

**若步驟 0 已顯示 `C:\HomeVibeCoding\shake-skills` 和 `ide-skills`、`openclaw-skills` 存在，可跳過本步。**

否則貼給 Agent：

```
在 Surface Pro 上確保 shake-skills repo 與目錄存在。

PowerShell 執行：

New-Item -ItemType Directory -Force -Path "C:\HomeVibeCoding"
cd C:\HomeVibeCoding
if (-not (Test-Path shake-skills)) { git clone https://github.com/imSHOW1024/shake-skills.git } else { cd shake-skills; git pull; cd .. }
if (Test-Path shake-skills) {
  New-Item -ItemType Directory -Force -Path "C:\HomeVibeCoding\shake-skills\ide-skills" | Out-Null
  New-Item -ItemType Directory -Force -Path "C:\HomeVibeCoding\shake-skills\openclaw-skills" | Out-Null
}
Get-ChildItem C:\HomeVibeCoding\shake-skills | Select-Object Name

回報目錄清單後停下來。
```

---

## 步驟 2：第一次備份（僅備份，不刪除）

**請在 Cursor Agent 中貼上以下指令。**

```
在 Surface Pro 上執行 shake-skills 的「第一次備份」。

PowerShell 執行（使用 $userHome = $env:USERPROFILE，不要改寫 $home）：

$userHome = $env:USERPROFILE
$date = Get-Date -Format "yyyyMMdd"

if (Test-Path "$userHome\.cursor\skills-cursor") {
  Compress-Archive -Path "$userHome\.cursor\skills-cursor" -DestinationPath "$userHome\skills-backup-cursor-$date.zip" -Force
  Write-Host "OK Cursor backup: $userHome\skills-backup-cursor-$date.zip"
} else { Write-Host "SKIP .cursor\skills-cursor not found" }

if (Test-Path "$userHome\.gemini\antigravity\skills") {
  Compress-Archive -Path "$userHome\.gemini\antigravity\skills" -DestinationPath "$userHome\skills-backup-antigravity-$date.zip" -Force
  Write-Host "OK Antigravity backup: $userHome\skills-backup-antigravity-$date.zip"
} else { Write-Host "SKIP .gemini\antigravity\skills not found" }

Get-ChildItem "$userHome\skills-backup-*.zip" -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Name) $($_.Length) bytes" }

回報備份檔名與大小後停下來等我確認。
```

---

## 步驟 3：建立 Junction（會刪除原有 skills 目錄並改為連結）

**備份確認無誤後再執行。** 貼給 Agent：

```
在 Surface Pro 上執行 shake-skills 的 Junction 設定（Prompt B）。

$ErrorActionPreference = "Stop"
$userHome = $env:USERPROFILE
$repoRoot = "C:\HomeVibeCoding\shake-skills"
$cursorTarget = "$userHome\.cursor\skills-cursor"
$cursorSource = Join-Path $repoRoot "ide-skills"
$antiTarget   = "$userHome\.gemini\antigravity\skills"
$antiSource   = Join-Path $repoRoot "ide-skills"
$openclawTarget = "$userHome\.openclaw\skills"
$openclawSource = Join-Path $repoRoot "openclaw-skills"

foreach ($p in @($repoRoot, $cursorSource, $antiSource, $openclawSource)) {
  if (-not (Test-Path $p)) { throw "Missing path: $p" }
}

function Test-ReparsePoint($path) {
  if (-not (Test-Path $path)) { return $false }
  $item = Get-Item $path -Force
  return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Ensure-Junction($target, $source) {
  Write-Host "Target: $target"
  Write-Host "Source: $source"
  if (Test-Path $target) {
    if (Test-ReparsePoint $target) { Write-Host "Already junction, skip."; return }
    Remove-Item $target -Recurse -Force
  }
  $parent = Split-Path $target -Parent
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
  cmd /c mklink /J "$target" "$source"
  Write-Host "OK"
}

Ensure-Junction -target $cursorTarget -source $cursorSource
Ensure-Junction -target $antiTarget   -source $antiSource
Ensure-Junction -target $openclawTarget -source $openclawSource

回報執行結果。
```

---

## 步驟 4：驗證

**貼給 Agent：**

```
在 Surface Pro 上驗證三個 Junction 是否正確。

$userHome = $env:USERPROFILE
Write-Host "=== .cursor\skills-cursor ==="
cmd /c dir "$userHome\.cursor\skills-cursor" 2>&1 | Select-Object -First 15
Write-Host "`n=== .gemini\antigravity\skills ==="
cmd /c dir "$userHome\.gemini\antigravity\skills" 2>&1 | Select-Object -First 15
Write-Host "`n=== .openclaw\skills ==="
cmd /c dir "$userHome\.openclaw\skills" 2>&1 | Select-Object -First 15

回報三個目錄的內容摘要（應看到 ide-skills / openclaw-skills 內的 skill 資料夾）。
```

---

## 日常同步（Surface Pro 之後每次使用）

- **取得最新 skills**：在 Cursor 終端機或 PowerShell 執行：
  ```powershell
  cd C:\HomeVibeCoding\shake-skills
  git pull
  ```
  因 Junction 已指向 repo，pull 後 Cursor / Antigravity / OpenClaw 會立即看到更新。

- **不改 skill 時**：只需定期 `git pull`，不需其他操作。

- **若在 Surface Pro 上改了某個 skill 並想同步回 G35CA**：
  ```powershell
  cd C:\HomeVibeCoding\shake-skills
  git add .
  git commit -m "update: [skill名] 簡短說明"
  git push
  ```
  之後在 G35CA 上 `git pull` 即可。

---

## 快速對照

| 步驟 | 內容 |
|------|------|
| 前置 | 建立 `C:\HomeVibeCoding`、clone repo、在 Cursor 開啟 repo 與本文件 |
| 0 | 環境與路徑檢查（不改檔） |
| 1 | 若 repo/目錄缺漏則 clone 或 pull 並建立 ide-skills / openclaw-skills |
| 2 | 第一次備份（zip 兩個 skills 目錄） |
| 3 | 建 Junction（刪除原目錄並指向 repo） |
| 4 | 驗證三個目標目錄內容 |
| 日常 | `git pull` 取得最新；有改動則 commit + push |

---

*與 G35CA 共用同一 repo 路徑 `C:\HomeVibeCoding\shake-skills`，Junction 目標一致，詳細架構見 `SYNC-SETUP.md`。*
