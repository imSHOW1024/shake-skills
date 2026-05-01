# HBR Taiwan Import Rules

## Canonical paths

- Skill root: `/Users/openclaw/.openclaw/workspace/skills/hbr-taiwan-obsidian-import`
- Default vault path: `/Users/openclaw/Documents/小龍女知識庫/10 Reading/HBR`
- Canonical dedupe key: frontmatter `source:`
- Default browser profile: `/tmp/hbr-login-profile`
- Browser requirement: Playwright persistent context with `channel: 'chrome'`

## URL normalization

Always normalize before dedupe or write:
- remove query strings
- remove hash fragments
- remove trailing slash

## Frontmatter schema

Keep this exact field set:

```yaml
---
title: "..."
title_en: "..."
source: https://www.hbrtaiwan.com/...
publisher: 哈佛商業評論（HBR Taiwan）
authors:
  - ...
date_published:
date_saved: YYYY-MM-DD
tags:
  - HBR
domains:
  -
status: complete
---
```

Notes:
- If author is unclear, use `(見文末)`.
- Leave `title_en` empty unless confidently available.
- `date_saved` should use local Asia/Taipei date.
- `domains` may stay empty-list style if no confident classification is available.

## Page-type handling

Never skip because a page is not an article.

Expected handling:
- `article`: import the main article body.
- `podcast`: keep the episode description, key body text, and any transcript-like text available.
- `video`: keep summary/body text available on page.
- `case-study`: preserve the readable summary and useful details.
- `special-topics`: preserve the landing-page summary and searchable takeaways.
- `visual-library`: preserve page summary and captions/text that remain useful in Obsidian.

If the page is short, be honest in the note body and label it as a summary/entry page instead of inventing missing content.

## Image filtering rules

**Reading-order preservation**: Images are extracted in DOM tree order and injected into the article body at their original positions (cover → text → figure → text → figure → text). A cover image that appears before the article text is prepended separately after all inline images. Empty `{{IMG}}` placeholders that cannot be resolved are silently dropped.

**Image include rules (what gets downloaded):**
- `imgs.cwgv.com.tw/pic/` — article body photos (inside `<a class="galleryBox">` links)
- `imgs.cwgv.com.tw/hbr_articles/<id>/<id>/preview/<id>.png` — the article's own cover image

**Image exclude rules (never downloaded):**
- `hbr_peoples` — author headshots (author bio section, not article body)
- `hbr_articles/.../preview/thumb/` — sidebar related-article thumbnails
- `hbr_journal` — sidebar journal covers
- `hbr_articles/.../preview/thumb/` — sidebar related-article thumbnail images (not article content)
- `hbr_common/slides_\d+` — sidebar slide thumbnails (not article content)
- `service.hbrtaiwan.com` — site service images
- Any image < 60×60px (tracking pixels)
- SVG, ICO, and non-image file types

**Image naming & placement:**
- Named `fig1.ext`, `fig2.ext`, … in DOM reading order
- Alt text becomes italic caption: `*alt text*`
- Saved to `images/` subdirectory alongside the `.md` file
- Images inside article content appear inline in reading order
- Cover image (outside article flow) prepended at the top

**Never download as article images:**
- Author headshots: URLs containing `hbr_peoples` (author profile photos belong to the author bio section, not the article body)
- Site chrome / UI elements: logos, nav icons, slide thumbnails, journal covers, footer images
- Tracking pixels: any image with both width < 60px AND height < 60px
- Non-image file types (SVG, ICO, etc.)

**Image include rules:**
- Only images inside the `<article>` element (or the main content root) should be considered article images
- If no article images are found in the article root, fall back to scanning the whole page with exclude rules applied

**Image naming:**
- Downloaded images are named `fig1.ext`, `fig2.ext`, ... in the order they appear in the article
- Alt text (not title attribute) becomes the italic caption: `*alt text*`
- Images are saved to `images/` subdirectory alongside the article's `.md` file

**Image injection in markdown:**
- Image blocks are placed at the top of the article body (`## 內文` section), before any prose, in the same order as they appeared in the source HTML
- Format: `![](images/figN.ext) *caption*` (one block per line)

## Author cleanup rules

Extract a clean author name from raw author strings that often include bio text.

**Role keywords that terminate a name** (truncate everything after the first occurrence):
```
博士候選人, 研究助理, 專案負責人, 專家合夥人, 博士後研究, 大使,
潛能計畫, 創辦人, 董事長, 管理合夥人, 執行長, 人資長,
學習長, 教務長, 副總裁, 總經理, 董事, 監事, 總監, 教授, 學者, 研究師
```

**Also stop at:** em-dash `—` anywhere in the string.

**Author deduplication:**
- After cleaning all author names, deduplicate by the first name token (case-insensitive)
- If two authors share the same first name token, keep both (they may be different people)
- Raw author strings (before cleaning) must not create duplicate entries in the final `authors:` list

## Noise line patterns

The following patterns identify lines that must be stripped from the article body:

```
/免費訂閱/i
/Apple Podcasts/i, /SoundOn/i, /Spotify/i, /KKBOX/i
/登入|登錄|註冊|續訂|立即訂閱|會員專區/i
/隱私權|服務條款|版權所有|Copyright/i
/^相關文章請見/i, /^延伸閱讀$/i, /^分享至/i, /^本篇文章主題$/i
/^更多關聯主題$/i, /^更多文章$/i, /^閱讀更多$/i
/^科技與分析$/i, /^領導與策略$/i, /^雜誌$/i
/Fajrul Islam\/Getty Images$/i    (or any /\/Getty Images$/i)
/^繼續閱讀全文$/i
/^可享每月三篇文章免費讀$/i
/哈佛商業評論數位版/i
/^人資新觀點$/i, /^最新文章$/i, /^主題分類$/i
/^個人學習$/i, /^精選專題$/i, /^影音$/i, /^個案研究$/i
/^觀念圖解$/i, /^雜誌.*書籍$/i, /^全文開放$/i
/^AI數位轉型$/i, /^新增資料夾$/i
/HBR[\u4e00-\u9fa5]*(?:英文版|編輯部|數位版)/i
/^(?:首頁|主題分類|領導|文章分類|人資新觀點)$/
/How AI Can Make Us Better Leaders$/i
/Vasilina Popova/i
/^\d{4}\/\d{2}\/\d{2}$/  (date-only lines)
```

## Cleanup rules

Strip obvious page chrome/noise before saving:
- login / subscribe / cookie / share / navigation prompts
- repeated title lines
- footer rails and related-content blocks
- Apple Podcasts / SoundOn / Spotify / KKBOX / podcast platform buttons
- `免費訂閱` and similar CTA text
- author-tail junk such as stray `HBR` fragments
- volume/time-player chrome and page-entry fragments
- Any line matching a pattern in the noise line patterns list above

## Overwrite policy

If normalized `source:` already exists in the vault:
- overwrite the existing file
- keep the existing filename if practical
- do not create another note for the same source

## Content Integrity Check

After extracting article body text, the script runs a post-processing check to detect paywall truncation:

| Signal | Threshold | Result |
|--------|-----------|--------|
| Body character count | < 3,000 chars | Flagged as truncated |
| Body ends with ellipsis | `…` / `⋯` / `...` | Flagged as truncated |
| Substantive paragraphs | < 5 paragraphs | Flagged as truncated |
| Sentence ending | No `。！？？」』` at end | Flagged as truncated |

When truncated is detected:
- `status: partial` (not `complete`)
- A blockquote warning `> ⚠️ ...` is prepended to the body

**Why it matters**: HBR Taiwan requires a live subscription session. When the cookie `academy-hbrtaiwan-com__zc` or `ci_session` expires, Playwright falls back to free-tier preview, producing truncated articles without any visible error.

**Resolution**: Re-login to HBR Taiwan in Chrome, then re-import.

## Pre-flight probe

Before running a batch import, the script probes the HBR Taiwan session to detect expired cookies / paywall before wasting tokens on truncated content.

**Trigger conditions:**
- `--probe` flag (any batch size)
- 3+ URLs queued (automatic guard for batch jobs)

**Probe logic:**
1. Fetch first URL via Playwright with the Chrome profile
2. Check for paywall text: `我要訂閱` / `已滿免費閱讀` / error page
3. Verify content length ≥ 2,500 chars
4. Exit code 1 with clear message if probe fails

**Use `--probe` to verify session before queuing a large batch:**
```bash
node scripts/import_hbr_links.mjs --probe '<any-hbr-url>' --profile /tmp/hbr-login-profile
```

## Output quality bar

A good import is:
- deduplicated by `source:`
- readable in Obsidian
- not obviously polluted by web chrome
- still useful when the source page is revisited months later
- `status: complete` (not `partial`)
