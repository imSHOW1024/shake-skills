# shake-skills

個人 AI skill 管理 repo，涵蓋 Claude Code、OpenClaw、Cursor、OpenAI Codex 等多平台。

## 快速開始

```bash
git clone https://github.com/imSHOW1024/shake-skills
```

依你的裝置選擇對應 profile：

| Profile | 裝置 | 說明 |
|---------|------|------|
| `profiles/openclaw-16mbp.yml` | 16" MBP M1 Max 32G | openclaw 主力機，全平台 |
| `profiles/vibe-coding-14mbp.yml` | 14" MBP M5 Max 128G | vibe coding 隨身機，Claude Code / Cursor |

## 目錄結構

```
shake-skills/
├── registry.yml          # 所有 skill 的單一真相來源（含 platform 標記）
├── profiles/             # 裝置 profile（決定裝哪些 skill）
│   ├── openclaw-16mbp.yml
│   └── vibe-coding-14mbp.yml
└── skills/               # 自維護 skill（local source）
    ├── emba-pptx/
    ├── wardrobe-obsidian/
    └── ...
```

## Platform 分類

- **universal** — 純 prompt / context，任何 AI agent 皆可用
- **claude-code** — Claude Code CLI 的 SKILL.md 格式
- **openclaw** — 依賴 openclaw runtime / browser profile
- **cursor** — Cursor IDE
- **codex** — OpenAI Codex CLI

詳細清單見 `registry.yml`。

## 安裝 skill

**clawhub 來源**（`source: clawhub`）：
```bash
clawhub install <slug>
```

**local 來源**（`source: local`）：直接使用 clone 下來的路徑，無需額外安裝步驟。

## 注意事項

- `memory-lancedb-pro-skill` 為 openclaw plugin，單獨管理，**不在此 repo**
- `dist/` 打包產物已加入 `.gitignore`，不版控
