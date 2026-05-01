---
name: hbr-taiwan-obsidian-import
description: Import, refetch, clean, deduplicate, and organize HBR Taiwan links into Obsidian notes under 10 Reading/HBR. Use when the user provides HBR Taiwan article/podcast/video/case-study/visual-library/special-topics URLs and wants them stored as readable Markdown with source-based dedupe, noisy text cleanup, and consistent frontmatter. This skill supports both agent-guided one-off handling and direct script execution for batch imports.
---

# HBR Taiwan Obsidian Import

Use this skill in hybrid mode: keep the procedural rules in mind, but prefer the bundled script whenever the task is mostly deterministic batch import.

## Choose the execution path

### Run the script directly

Prefer `scripts/import_hbr_links.mjs` when the task is one or more HBR Taiwan URLs and the goal is to import or refresh notes with the standard schema.

Use the script especially for:
- multiple URLs at once
- routine refresh / overwrite by `source:`
- article, podcast, video, case-study, special-topics, or visual-library pages
- jobs where Playwright should fetch the logged-in page consistently

Example:

```bash
cd /Users/openclaw/.openclaw/workspace/skills/hbr-taiwan-obsidian-import
node scripts/import_hbr_links.mjs \
  'https://www.hbrtaiwan.com/article/24572/when-working-with-ai-act-like-a-decision-maker-not-a-tool-user' \
  'https://www.hbrtaiwan.com/podcast/23981/chifei-fan'
```

Or via stdin:

```bash
printf '%s\n' \
  'https://www.hbrtaiwan.com/video/12345/example' \
  'https://www.hbrtaiwan.com/special-topics/54321/example' \
| node scripts/import_hbr_links.mjs
```

Useful options:
- `--dry-run` to fetch/parse without writing
- `--probe` to check login session validity before running import
- `--vault <path>` to override the Obsidian target folder
- `--profile <path>` to override the Chrome profile path

## Keep the skill rules in control

Even when the script runs, enforce these rules:
1. Normalize URL first: strip query and trailing slash.
2. Use frontmatter `source:` as the dedupe key.
3. Overwrite the existing note for the same normalized `source:`.
4. Preserve the standard frontmatter fields and ordering.
5. Do not skip non-article page types; save the most useful readable body available.
6. Remove obvious chrome/noise before saving.

## Sub-agent / spawned task behavior

Follow the **universal Sub-Agent Dispatch principle** (AGENTS.md): before starting, the sub-agent must read `SKILL.md` and `references/hbr-import-rules.md` in full and treat those files as the source of truth.

Specific to this skill:
- Use `node scripts/import_hbr_links.mjs` directly — do not rewrite fetch/parse/save logic
- After import, report: success count, failure count, and list of file titles

## Content Integrity Check

The import script includes a **post-processing content integrity check** that automatically detects truncated articles:

Truncation signals checked:
- Body text < 3,000 characters (article too short)
- Body ends with `...` / `…` / `⋯` (mid-sentence cut)
- Fewer than 5 substantive paragraphs
- No proper sentence-ending punctuation

When truncated:
- `status: partial` (instead of `complete`)
- A `> ⚠️ ...` blockquote warning is prepended to the body, explaining the likely cause
- The script still completes successfully (does not fail), but reports the partial status

**When you see partial articles**: This means the HBR Taiwan login session has expired. To fix:
1. Open Chrome and navigate to `https://www.hbrtaiwan.com`
2. Log in with the subscribed account
3. Keep the tab open (or close Chrome normally) — Playwright will reuse the same Chrome profile at `/tmp/hbr-login-profile`
4. Re-run the import

The key cookies are `academy-hbrtaiwan-com__zc` (subscription token) and `ci_session` (login session) — both expire. Manual re-login is currently the only fix.

## Use manual skill reasoning instead of the script when needed

Do not force the script if the task needs human judgement beyond deterministic import, for example:
- the user wants custom tags/domains, manual summarization, or rewritten structure
- the page content is malformed and needs hand-cleaning
- Playwright/login is unavailable and another recovery path is needed
- the output needs to be merged into a broader knowledge workflow, not just imported as-is

When doing manual cleanup, still follow `references/hbr-import-rules.md`.

## Script expectations

The script should:
- accept URLs from argv or stdin
- use Playwright persistent Chrome profile at `/tmp/hbr-login-profile` by default
- scan `/Users/openclaw/Documents/小龍女知識庫/10 Reading/HBR` for existing `source:` values
- overwrite matching notes instead of creating duplicates
- emit a concise execution summary with success/failure counts and file paths

## Pre-flight probe & session guard

The script includes a **pre-flight probe** that validates the HBR Taiwan login session before committing to a batch import.

**When it runs:**
- Automatic when 3 or more URLs are queued (batch import guard)
- Explicit with `--probe` flag (for any batch size)

**What it checks:**
1. Launches Chrome profile, fetches the first URL
2. Looks for paywall signals: `我要訂閱` / `已滿免費閱讀` / error page text
3. Checks content length (≥ 2,500 chars as proxy for full content)

**Outcomes:**
| Condition | Result |
|---|---|
| Probe PASS | Prints `✅ Session OK` → continues to import |
| Probe FAIL | Prints clear reason → exits code 1 before wasting tokens |
| `--probe` mode | Only runs probe, then exits. Use to verify session before queuing a large batch |
| Content truncated mid-batch | Article gets `⚠️ PARTIAL` flag in output, exit code 2 |

**Session refresh:** If probe fails, the HBR login session has expired. To refresh:
1. Open Chrome → go to `https://www.hbrtaiwan.com` → log in with subscribed account
2. Keep Chrome open (or close normally — Playwright will reuse the same profile)
3. Re-run the import

**Note:** The probe and the import itself both require Chrome to be the running process hosting the profile. Keep Chrome open in the background with an active HBR session before running a batch.

## References

Read `references/hbr-import-rules.md` when you need the exact note schema, cleanup rules, or page-type expectations.
