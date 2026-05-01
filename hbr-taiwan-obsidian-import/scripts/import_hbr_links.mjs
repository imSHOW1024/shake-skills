#!/usr/bin/env node

import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import https from 'node:https';
import http from 'node:http';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const vaultDir = '/Users/openclaw/Documents/小龍女知識庫/10 Reading/HBR';
// Default profile path — if /tmp/hbr-login-profile exists and has valid session cookies,
// the script uses it directly without needing an external Chrome.
// On first run with no profile, it will attempt auto-login using credentials
// from environment variables HBR_EMAIL / HBR_PASSWORD (if set).
const browserProfileDir = '/tmp/hbr-login-profile';
const hbrLoginUrl = 'https://service.hbrtaiwan.com/login?action=frontlogin&rdurl=https://www.hbrtaiwan.com/';
const hbrEmail = process.env.HBR_EMAIL || '';
const hbrPassword = process.env.HBR_PASSWORD || '';
const publisher = '哈佛商業評論（HBR Taiwan）';
const defaultTags = ['HBR'];
const defaultDomains = [];
const usage = `Usage:
  node scripts/import_hbr_links.mjs <url1> <url2> ...
  printf '%s\n' '<url1>' '<url2>' | node scripts/import_hbr_links.mjs

Options:
  --vault <path>         Override Obsidian output folder
  --profile <path>       Override Chrome user data dir (default: ${browserProfileDir})
  --cdp                  Connect to already-running Chrome via CDP (Chrome must be launched with --remote-debugging-port=9222)
  --probe                Run session probe only, then exit
  --dry-run              Fetch and parse but do not write notes
  --help                 Show this help
`;

function normalizeUrl(input) {
  const url = new URL(input.trim());
  url.hash = '';
  url.search = '';
  let normalized = url.toString();
  if (normalized.endsWith('/')) normalized = normalized.slice(0, -1);
  return normalized;
}

function escapeYamlString(value) {
  return JSON.stringify(String(value ?? ''));
}

function slugifyFilename(input) {
  const cleaned = String(input || 'HBR Taiwan').replace(/[\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim();
  return (cleaned || 'HBR Taiwan').slice(0, 120);
}

function uniqueNonEmpty(values) {
  return [...new Set((values || []).map((v) => String(v || '').trim()).filter(Boolean))];
}

function formatYamlList(values) {
  if (!values.length) return '  -';
  return values.map((value) => `  - ${String(value).includes(':') ? JSON.stringify(value) : value}`).join('\n');
}

function todayLocal() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

/**
 * Extract a clean author name from raw string (which often includes bio text).
 * Strategy: find the FIRST role/org keyword and truncate everything after it.
 * Do NOT split on middle dots that are part of names.
 */
/**
 * Clean an author raw string into a minimal name string.
 * Removes: title prefixes, affiliation parentheticals, role descriptions,
 * em-dashes, and any trailing non-name text.
 */
function extractCleanAuthorName(raw) {
  const s = String(raw || '').replace(/\u00a0/g, ' ').trim();
  if (/^(?:哈佛商業評論|HBR|哈佛)$/i.test(s)) return '';
  if (!s) return '';

  let name = s
    .replace(/^(作者|By|撰文|文[:：]\s*)/i, '')
    .replace(/\s+/g, ' ')
    .trim();

  // Remove title / role prefixes (match from beginning only)
  const titlePrefixes = [
    /^教授$/, /^博士$/, /^碩士$/, /^律師$/,
  ];

  // Remove affiliation blocks: (Org Name) or （Org Name） from the end
  // Covers: (Boston Consulting Group, BCG), （Boston Consulting Group, BCG）， etc.
  // Also handles: (University of Pennsylvania), （University of California, Riverside）
  name = name
    .replace(/[（(][^）)]*[BCG][^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*University[^）)]*[）)]\s*/gi, '')
    .replace(/[（(][^）)]*大學[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*商學院[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*研究所[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*學院[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*亨德森[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*MacArthur[^）)]*[）)]\s*/gi, '')
    .replace(/[（(][^）)]*華頓[^）)]*[）)]\s*/g, '')
    .replace(/[（(][^）)]*King[^）)]*[）)]\s*/gi, '')
    .replace(/[（(][^）)]{2,}[）)]\s*/g, '') // any remaining long (...) blocks
    .trim();

  // Truncate at role keywords (stop at first occurrence)
  const rolePatterns = [
    '潛能計畫', '創辦人', '董事長', '管理合夥人', '執行長', '人資長',
    '學習長', '教務長', '副總裁', '總經理', '董事', '監事', '總監',
    '博士候選人', '研究助理', '專案負責人', '專家合夥人', '研究師',
    '博士後研究', '大使', '學者', '教授', '心理學家', '醫學博士',
  ];

  let earliestRoleIdx = -1;
  let earliestRoleName = '';
  for (const role of rolePatterns) {
    const idx = name.indexOf(role);
    if (idx !== -1 && (earliestRoleIdx === -1 || idx < earliestRoleIdx)) {
      earliestRoleIdx = idx;
      earliestRoleName = role;
    }
  }

  // Also stop at em-dash
  const dashIdx = name.indexOf('—');
  if (dashIdx !== -1 && (earliestRoleIdx === -1 || dashIdx < earliestRoleIdx)) {
    earliestRoleIdx = dashIdx;
    earliestRoleName = '';
  }

  // Stop at affiliation ownership suffix ("的公司", "的大學", "的學院", etc.)
  for (const affix of ['的公司', '的大學', '的學院', '的研究所', '的醫院']) {
    const idx = name.indexOf(affix);
    if (idx !== -1 && (earliestRoleIdx === -1 || idx < earliestRoleIdx)) {
      earliestRoleIdx = idx;
      earliestRoleName = affix;
    }
  }

  if (earliestRoleIdx > 0) {
    name = name.slice(0, earliestRoleIdx).trim();
  }

  // Last resort: strip remaining company / university suffixes and dangling affixes
  name = name
    // Remove trailing "的公司" — note: string ends with "公司+的" (company + possessive), NOT "的+company"
    .replace(/(?:公司|大學|學院|研究所|醫院)的$/, '')
    .trim()
    // Remove "XX顧問公司" (no 的 after) from end
    .replace(/[顧管理營業股]公司$/, '')
    // Remove university name followed by department text: "XX大學XXXX"
    .replace(/\s+[^\s]*大學\s*[^\s]*/g, '')
    // Remove trailing company/university fragments
    .replace(/\s+[A-Za-z][^\s]*(?:公司|學院|研究所)$/, '')
    .trim();

  // If name is suspiciously short, use first 3 tokens as fallback
  if (name.length < 4) {
    name = s.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim().split(/\s+/).slice(0, 3).join(' ');
  }

  return name;
}

function cleanAuthor(raw) {
  return extractCleanAuthorName(raw);
}

function cleanInlineText(text) {
  return String(text || '')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

const noisePatterns = [
  /免費訂閱/i,
  /Apple Podcasts/i,
  /SoundOn/i,
  /Spotify/i,
  /KKBOX/i,
  /Podcasts?\s*-\s*YouTube/i,
  /登入|登錄|註冊|續訂|立即訂閱|會員專區/i,
  /隱私權|服務條款|版權所有|Copyright/i,
  /^相關文章請見/i,
  /^0 seconds of /i,
  /^Volume \d+%/i,
  /^Episode$/i,
  /^更多文章$/i,
  /^閱讀更多$/i,
  /^延伸閱讀$/i,
  /^分享至/i,
  /^本篇文章主題$/i,
  /^更多關聯主題$/i,
  /哈佛商業評論數位版/i,
  /^人資新觀點$/i,
  /^最新文章$/i,
  /^主題分類$/i,
  /^個人學習$/i,
  /^精選專題$/i,
  /^影音$/i,
  /^個案研究$/i,
  /^觀念圖解$/i,
  /^雜誌.*書籍$/i,
  /^全文開放$/i,
  /^AI數位轉型$/i,
  /^新增資料夾$/i,
  /HBR[\u4e00-\u9fa5]*(?:英文版|編輯部|數位版)/i,
  /^(?:首頁|主題分類|領導|文章分類|人資新觀點)$/,
  /^How AI Can Make Us Better Leaders$/i,
  /^Vasilina Popova/i,
  /^\d{4}\/\d{2}\/\d{2}$/,
  /^拉斯穆斯/,
  /^雜誌$/i,
  /^科技與分析$/i,
  /^領導與策略$/i,
  /\/Getty Images$/i,
  /^繼續閱讀全文$/i,
  /^可享每月三篇文章免費讀$/i,
  /^\d{4}年\d{1,2}月號-/i,       // "2026年4月號-搶救一線缺工潮"
  /^訂閱數位版$/i,
  /^訂閱數位版即可立即無限暢讀$/i,
  /^全站優質文章、影音等豐富內容$/i,
  /^每月定期扣款，隨時可線上申請暫停扣款$/i,
  /^搶救一線缺工潮$/i,
  /^跨界領導力$/i,
  /^[A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+$/,  // English name only lines
  /^生成式人工智慧$/i,
  /^When Using AI Leads to "Brain Fry"$/i,
  /^Listen To Your Gut$/i,
  /^LLMs Are Overtaking Search/i,
  /^Gen AI Is Threatening/i,
  /^AI Doesn\u2019t Reduce Work/i,
  /^A Guide to Building Change/i,
  /^Should You Stop Investing in AI$/i,
  /^Preparing Your Brand for Agentic AI$/i,
  /^Life\u2019s Work: An Interview with Jimmy Wales$/i,
  /^Jimmy Wales$/i,
  /^How Gen Z Uses Gen AI$/i,
  // Concatenated author names (multiple full names joined without separator)
  // These appear as single lines where Chinese and Western names are adjacent in flex layout
  // Pattern: 2+ Chinese·Western name pairs with no space between Western→Chinese
  /^[^A-Za-z一-鿿]{0,10}[．・][^\n]{5,60}[．・][^\n]{5,60}[．・]/,
  // Concatenated flex author line: matches "Julie's nameFirstName LastNameChineseName..."
  /^[A-Z][a-z]+\s+[A-Za-z\s（\uff09\u0020-\u007e]+[A-Z][a-z]+\s+[A-Za-z\u4e00-\u9fff\uff08\uff09\u0020-\u007e]+[A-Z][a-z]+\s+/,
  // Audio player / TTS noise (timestamps, speed buttons, play/pause controls)
  /^\d{2}:\d{2}\s*\/\s*\d{2}:\d{2}$/,           // "00:02 / 25:28"
  /^\d{1,2}:\d{2}$/,                              // standalone timestamps "00:02"
  /^[\d\.]+\s*[×x]\s*$/,                        // playback speeds: "1.0 x", "0.8 x"
  /^[\d\.]+\s*×\s*$/,                           // "1.5 ×"
  /^聽文章$/i,                                     // audio player button label
  /^播放$/i,                                       // play button
  /^加入播放清單$/i,
  /^\d+\/\d+$/,                                  // "25/28" page-like fractions from audio
  // Audio player bar text (appears as inline text inside article body container)
  // Audio player bar: various combinations of button labels
  /^播放\s+全文(\s+收藏)?(\s+放大縮小)?\s*$/,
  /^全文\s+收藏(\s+放大縮小)?(\s+購買)?$/,
  /^收藏\s+放大縮小(\s+購買)?$/,
  /^放大縮小\s+購買$/,
  // Paywall / subscription inline text (appears inside articleCtn.articleBottom)
  /^閱讀篇數已達上限。$/,
  /^訂閱數位版即可立即無限暢讀全站優質文章、影音等豐富內容。$/,
  // Article bottom author bio / redirect noise
  /^資料跳轉中\.\.\.$/,
  // Audio player / purchase bar button labels merged by DOM normalize
  // (original text nodes separated by divs; divs removed, adjacent text merged)
  /^播放\s+全文\s+收藏\s+放大\s+縮小\s+購買$/,
  /^播放\s+全文\s+收藏\s+放大縮小\s+購買$/,
  /^播放\s+全文\s+放大\s+縮小\s+購買$/,
  /^播放\s+全文\s+放大縮小\s+購買$/,
  /^全文\s+收藏\s+放大\s+縮小$/,
  /^全文\s+收藏\s+放大縮小$/,
  /^收藏\s+放大\s+縮小\s+購買$/,
  /^收藏\s+放大縮小\s+購買$/,
  /^放大\s+縮小\s+購買$/,
  /^放大縮小\s+購買$/,
  /^Post\s+Post\s+Share$/,
  /^Post\s+Share$/,
  /^Share$/,
];  // ← noisePatterns end

function isNoiseLine(text) {
  // Strip common list/heading prefixes before checking
  // Handles ASCII hyphen, em-dash, en-dash, bullet, and asterisk markers
  const line = cleanInlineText(text)
    .replace(/^[\-–—·•◦‹›«»●○◆◇★®\s]+/, '')
    .replace(/^#+\s*/, '');

  if (!line) return true;
  if (line.length <= 2 && /\d+/.test(line)) return true;
  return noisePatterns.some((pattern) => pattern.test(line));
}

function parseArgs(argv) {
  const urls = [];
  let dryRun = false;
  let vault = vaultDir;
  let profile = browserProfileDir;
  let probeOnly = false;
  let useCdp = false;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      console.log(usage);
      process.exit(0);
    }
    if (arg === '--dry-run') {
      dryRun = true;
      continue;
    }
    if (arg === '--probe') {
      probeOnly = true;
      continue;
    }
    if (arg === '--cdp') {
      useCdp = true;
      continue;
    }
    if (arg === '--vault') {
      vault = argv[i + 1];
      i += 1;
      continue;
    }
    if (arg === '--profile') {
      profile = argv[i + 1];
      i += 1;
      continue;
    }
    urls.push(arg);
  }

  return { urls, dryRun, probeOnly, useCdp, vault, profile };
}

/**
 * Probe the HBR Taiwan session to verify login status before batch processing.
 * Returns { ok, reason, chars }.
 * - ok=true: session looks valid, proceed with import.
 * - ok=false: session is expired or inaccessible; abort with reason.
 */
async function probeSession(browserProfile, testUrl) {
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launchPersistentContext(browserProfile, {
    headless: true,
    viewport: { width: 1440, height: 900 },
  });
  try {
    const page = browser.pages()[0] || await browser.newPage();
    await page.goto(testUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(2000);
    const bodyText = await page.evaluate(() => document.body.innerText);

    // Check for REAL paywall / not-logged-in signals (not cosmetic nav text)
    // "我要訂閱" appears in the nav bar for ALL users (logged-in or not) — not a paywall signal
    // Real paywall: "閱讀篇數已達上限" OR "已滿免費閱讀" appears as a blocking message
    // Real logout: the page shows login form instead of article content
    const isPaywalled =
      bodyText.includes('閱讀篇數已達上限') ||
      bodyText.includes('已滿免費閱讀') ||
      bodyText.includes('此篇文章必須訂閱');
    const isLoggedOut = !bodyText.includes('個人學習');  // "個人學習" only appears for logged-in users
    const hasContent = bodyText.length >= 2500;

    await browser.close().catch(() => {});

    if (isPaywalled) {
      return {
        ok: false,
        reason: '此帳號當月份免費閱讀額度已用完（顯示「閱讀篇數已達上限」），請下个月再試，或訂閱數位版',
        chars: bodyText.length,
      };
    }
    if (isLoggedOut) {
      return {
        ok: false,
        reason: 'Session 已過期，請重新執行登入流程（目前不支援自動重登，請手動登入後再試）',
        chars: bodyText.length,
      };
    }
    if (!hasContent) {
      return {
        ok: false,
        reason: `內容過短（${bodyText.length} 字），可能是文章本身較短或載入不完整`,
        chars: bodyText.length,
      };
    }
    return { ok: true, reason: 'session valid', chars: bodyText.length };
  } catch (err) {
    try { await browser.close().catch(() => {}); } catch (_) {}
    return { ok: false, reason: `瀏覽器錯誤: ${err.message}`, chars: 0 };
  }
}

async function readStdin() {
  if (process.stdin.isTTY) return '';
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

async function collectUrls(argvUrls) {
  const stdin = await readStdin();
  const inputs = [...argvUrls, ...stdin.split(/\r?\n|\s+/)].map((s) => s.trim()).filter(Boolean);
  const normalized = [];
  const errors = [];
  for (const input of inputs) {
    try {
      const url = normalizeUrl(input);
      if (!/^https?:\/\/www\.hbrtaiwan\.com\//.test(url)) {
        errors.push(`skip non-HBR-Taiwan URL: ${input}`);
        continue;
      }
      normalized.push(url);
    } catch {
      errors.push(`skip invalid URL: ${input}`);
    }
  }
  return { urls: [...new Set(normalized)], inputWarnings: errors };
}

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    throw new Error([
      'Missing dependency: playwright',
      'Install it from the workspace root or an accessible parent directory, for example:',
      '  cd /Users/openclaw/.openclaw/workspace && npm install playwright',
      'Then re-run this script. Also make sure Google Chrome is installed, because the script launches channel: \'chrome\'.',
    ].join('\n'));
  }
}

async function walkMarkdownFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await walkMarkdownFiles(fullPath));
    } else if (entry.isFile() && fullPath.endsWith('.md')) {
      files.push(fullPath);
    }
  }
  return files;
}

async function buildExistingSourceMap(dir) {
  const sourceMap = new Map();
  try {
    const files = await walkMarkdownFiles(dir);
    for (const file of files) {
      const content = await fs.readFile(file, 'utf8');
      const match = content.match(/^source:\s*(.+)$/m);
      if (!match) continue;
      try {
        sourceMap.set(normalizeUrl(match[1]), file);
      } catch {
        // ignore malformed source frontmatter
      }
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  return sourceMap;
}

function buildFrontmatter(meta) {
  const authors = uniqueNonEmpty(meta.authors.length ? meta.authors : ['(見文末)']);
  const tags = uniqueNonEmpty([...defaultTags, ...(meta.tags || [])]);
  const domains = uniqueNonEmpty(meta.domains || defaultDomains);
  const lines = [
    '---',
    `title: ${escapeYamlString(meta.title)}`,
    `title_en: ${escapeYamlString(meta.title_en || '')}`,
    `source: ${meta.source}`,
    `publisher: ${publisher}`,
    'authors:',
    formatYamlList(authors),
    `date_published: ${meta.date_published || ''}`,
    `date_saved: ${meta.date_saved}`,
    'tags:',
    formatYamlList(tags),
    'domains:',
    formatYamlList(domains),
    `status: ${meta.status || 'complete'}`,
    '---',
  ];
  return lines.join('\n');
}

function composeNote(meta) {
  const frontmatter = buildFrontmatter(meta);
  const body = cleanInlineText(meta.body || `來源頁型：${meta.page_type || 'page'}\n\n此頁可擷取的正文有限，已保留標題與摘要。`);
  return `${frontmatter}\n\n# ${meta.title}\n\n## 內文\n\n${body}\n`;
}

function detectPageTypeFromUrl(url) {
  const pathname = new URL(url).pathname;
  const first = pathname.split('/').filter(Boolean)[0] || 'article';
  return first;
}

/**
 * Download an image URL to destPath. Returns basename on success, null on failure.
 */
function downloadImage(imageUrl, destPath) {
  return new Promise((resolve) => {
    try {
      const file = fsSync.createWriteStream(destPath);
      const protocol = imageUrl.startsWith('https') ? https : http;
      const req = protocol.get(imageUrl, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' },
        timeout: 15000,
      }, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          file.close();
          fsSync.unlinkSync(destPath);
          // Follow redirect up to 3 hops
          downloadImage(response.headers.location, destPath).then(resolve).catch(() => resolve(null));
          return;
        }
        if (response.statusCode !== 200) {
          file.close();
          try { fsSync.unlinkSync(destPath); } catch {}
          resolve(null);
          return;
        }
        response.pipe(file);
        file.on('finish', () => {
          file.close(() => resolve(path.basename(destPath)));
        });
        file.on('error', () => {
          file.close();
          try { fsSync.unlinkSync(destPath); } catch {}
          resolve(null);
        });
      });
      req.on('error', () => {
        try { file.close(); fsSync.unlinkSync(destPath); } catch {}
        resolve(null);
      });
      req.on('timeout', () => {
        req.destroy();
        try { file.close(); fsSync.unlinkSync(destPath); } catch {}
        resolve(null);
      });
    } catch {
      resolve(null);
    }
  });
}

async function extractPage(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1500);

  return page.evaluate(({ url, fallbackPageType }) => {
    const clean = (value) => String(value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();

    // Noise phrases and stripNoiseFromText for structural container child walk
    const noisePhrases = [
      'HBR Staff/Runstudio Getty Images',
      'Getty Images',
      '聽文章',
      '閱讀篇數已達上限。',
      '訂閱數位版即可立即無限暢讀全站優質文章、影音等豐富內容。',
      '立即訂閱',
      '了解更多',
      '加入播放清單',
      '文章購買紀錄',
    ];
    const stripNoiseFromText = (text) => {
      const parts = [text];
      for (const phrase of noisePhrases) {
        const newParts = [];
        for (const part of parts) {
          const split2 = part.split(phrase);
          for (const s of split2) {
            const trimmed = s.trim();
            if (trimmed) newParts.push(trimmed);
          }
        }
        parts.splice(0, parts.length, ...newParts);
      }
      const shortNoise = ['播放', '全文', '收藏', '放大', '縮小', '購買', 'Post', 'Share'];
      const filteredParts = [];
      for (const part of parts) {
        let p = part;
        for (const tok of shortNoise) { p = p.split(tok).join(''); }
        p = p.trim();
        if (p) filteredParts.push(p);
      }
      return filteredParts.join(' ');
    };

    const textOf = (selector) => clean(document.querySelector(selector)?.textContent || '');
    const attrOf = (selector, attr) => clean(document.querySelector(selector)?.getAttribute(attr) || '');
    const allText = (selector) => Array.from(document.querySelectorAll(selector)).map((el) => clean(el.textContent)).filter(Boolean);
    const allAttr = (selector, attr) => Array.from(document.querySelectorAll(selector)).map((el) => clean(el.getAttribute(attr) || '')).filter(Boolean);
    const bySelectors = (selectors) => {
      for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el && clean(el.textContent).length > 40) return el;
      }
      return null;
    };

    const title = attrOf('meta[property="og:title"]', 'content') || textOf('h1');
    const description = attrOf('meta[name="description"]', 'content') || attrOf('meta[property="og:description"]', 'content');
    const published = attrOf('meta[property="article:published_time"]', 'content') || attrOf('time[datetime]', 'datetime') || textOf('time');

    // Extract author names — target only the name element, NOT the bio
    const authorNames = [
      ...allAttr('meta[name="author"]', 'content'),
      ...allText('[rel="author"]'),
      ...allText('.author-name, .article-author-name, [class*="author-name"]'),
      // Fallback: full author block, will be cleaned downstream
      ...allText('.author, .article-author, .post-author, .writers, .writer, .podcast-host, .video-author'),
      ...allText('[class*="author"]'),
    ].filter(Boolean);

    // Extract images from the article body with their src and alt
    // Use the article body container to avoid sidebar/related-article images
    // NOTE: .articleCtn.articleBottom (body with full text + images) comes FIRST
    // because .articleBox > .container-xl is only a 320-char header with no body content
    const articleRoot = bySelectors([
      '.articleCtn.articleBottom',          // HBR Taiwan: full article body (7043 chars, 12 imgs)
      '.articleCtn',                        // HBR Taiwan: article section (fallback)
      '.articleBox > .container-xl',        // HBR Taiwan: first child container (header only)
      'article',
      'main article',
      'main',
      '.article-detail',
      '.article-content',
      '.post-content',
      '.entry-content',
      '.content-detail',
    ]);

    const images = [];
    // Image URL patterns to exclude (site chrome / UI elements)
    const imgExcludePatterns = [
      /logo/i,           // logos
      /navIcon/i,        // nav icons
      /\/icons\//i,      // icon SVGs in /icons/
      /\/svg\//i,        // SVG images
      /hbr_journal/i,    // journal covers (sidebar)
      /hbr_common\/slides_\d+/i,  // slide thumbnails (sidebar) — article figures use pic/
      /publication/i,    // publication covers
      /\/article\/\d+\/article$/i, // self-referencing URL
      /buy\.svg|facebook|line2|copy_link|keep|word-2/i, // UI buttons
      /footer|pic\/thumbs/i, // footer images
      /service\.hbrtaiwan\.com/i,  // site service images (fig6,7,8)
      // Sidebar article thumbnails: hbr_articles/.../preview/thumb/ (related articles section)
      /hbr_articles\/\d+\/\d+\/preview\/thumb\/.+\.(jpe?g|png|webp)/i,
      /hbr_peoples/i,    // author headshots — belong to bio, not article body
    ];

    const imgIncludePatterns = [
      /imgs\.cwgv\.com\.tw\/pic\//i,   // article body photos (inside galleryBox links)
      // Article cover image: hbr_articles/<id>/<id>/preview/<id>.png (the article's own cover)
      // Also matches: hbr_articles/<year>/<id>/preview/<id>.png (2026=22 in base-36)
      /imgs\.cwgv\.com\.tw\/hbr_articles\/\d+\/\d+\/preview\//i,
    ];

    if (articleRoot) {
      articleRoot.querySelectorAll('img').forEach((img) => {
        const rawSrc = img.getAttribute('src') || img.getAttribute('data-src') || '';
        const src = rawSrc.trim();
        const alt = clean(img.getAttribute('alt') || img.getAttribute('title') || '');
        // Skip tiny tracking pixels
        const w = parseInt(img.getAttribute('width') || '0', 10);
        const h = parseInt(img.getAttribute('height') || '0', 10);
        if (w > 0 && h > 0 && w < 60 && h < 60) return;
        if (!src) return;
        // Skip non-image file types
        if (!/\.(jpe?g|png|gif|webp|avif)/i.test(src)) return;
        // Apply include rules if patterns are defined (at least one match)
        const isIncluded = imgIncludePatterns.some((p) => p.test(src));
        const isExcluded = imgExcludePatterns.some((p) => p.test(src));
        if (isExcluded && !isIncluded) return;
        // If we have include rules and none match, skip
        if (imgIncludePatterns.length > 0 && !isIncluded && !isExcluded) return;
        // Deduplicate by URL
        if (images.some((e) => e.src === src)) return;
        images.push({ src, alt });
      });
    }

    // Also scan the whole page for article-relevant images if none found in article root
    if (images.length === 0) {
      document.querySelectorAll('img').forEach((img) => {
        const rawSrc = img.getAttribute('src') || '';
        const src = rawSrc.trim();
        if (!src) return;
        if (!/\.(jpe?g|png|gif|webp|avif)/i.test(src)) return;
        const isIncluded = imgIncludePatterns.some((p) => p.test(src));
        const isExcluded = imgExcludePatterns.some((p) => p.test(src));
        if (isExcluded && !isIncluded) return;
        const w = parseInt(img.getAttribute('width') || '0', 10);
        const h = parseInt(img.getAttribute('height') || '0', 10);
        if (w > 0 && h > 0 && w < 60 && h < 60) return;
        if (images.some((e) => e.src === src)) return;
        images.push({ src, alt: clean(img.getAttribute('alt') || '') });
      });
    }

    const root = bySelectors([
      '.articleCtn.articleBottom',     // HBR Taiwan: full article body (exclude audio player in header sibling)
      '.articleCtn',                   // HBR Taiwan: article section
      '.articleBox > .container-xl',   // HBR Taiwan: first child container (header only, fallback)
      '.articleBox',
      '.articleCenter',
      '.container-xl.articleSet',
      '.mainContainer',
      '.podcast-detail', '.video-detail', '.case-study-detail',
      '.special-topics-detail', '.visual-library-detail',
      '#__next main', 'body',
    ]);

    const removeSelectors = [
      'script, style, noscript, svg, canvas, form, iframe, footer, nav, aside',
      '[aria-label="breadcrumb"]',
      '[class*="share"]', '[class*="social"]', '[class*="subscribe"]',
      '[class*="login"]', '[class*="member"]', '[class*="cookie"]',
      '[class*="recommend"]', '[class*="related"]',
      '[class*="footer"]', '[class*="header"]',
      '[id*="footer"]', '[id*="header"]',
      '.advertisement, .ad, .ads',
      'button',
      // Author metadata blocks
      '[class*="author-bio"]', '[class*="author-section"]',
      '[class*="author-name"]', '[class*="writers"]', '[class*="writer"]',
      '[class*="article-author"]', '[class*="post-author"]',
      '[class*="article-tag"]', '[class*="article-category"]',
      '[class*="article-meta"]', '[class*="article-info"]',
      '[class*="magazine-issue"]', '[class*="issue-tag"]',
      '[class*="subscription"]', '[class*="paywall"]',
      '[class*="tag-list"]', '[class*="category-list"]',
      // Tag pills / category pills in article header
      '.article-tags a', '.tag-pill', '[class*="tag-pill"]',
      // Audio player / TTS interface elements
      '[class*="tts-timer"]', '[class*="tts-text"]',
      '[class*="speed"]',
      '[class*="tts-"]', '[class*="audio-"]', '[class*="media-player"]',
      // Subscription / paywall modals
      '[class*="modal"]',
      '[class*="newDropdownBoxMenu"]',
      '[class*="dropdownBoxMenu"]',
      // Content-area noise: sidebar-like sections inside article root
      '[class*="articleBottom"]',
      '[class*="after_post_content"]',
      '[class*="post-bottom"]',
      '[class*="adBox"]',
      // Related articles sidebar within article content
      '[class*="similerArticle"]',
      '[class*="similarArticle"]',
      '[class*="relatedArticle"]',
    ];

    const container = root?.cloneNode(true) || document.body.cloneNode(true);
    for (const selector of removeSelectors) {
      container.querySelectorAll(selector).forEach((el) => el.remove());
    }

    const blocks = [];
    const push = (value) => {
      const text = clean(value);
      if (!text) return;
      blocks.push(text);
    };

    // Walk DOM in tree order: collect text blocks AND image positions together.
    // This preserves the original reading order: 封面→內文→圖→內文→圖→內文
    const contentItems = [];
    const BLOCK_TAGS = new Set(['H1','H2','H3','H4','P','LI','BLOCKQUOTE','DIV','SECTION']);

    // Split element text content by <br> tags to preserve paragraph boundaries
    function splitByBr(el) {
      const parts = [];
      let current = [];
      for (const node of el.childNodes) {
        if (node.nodeType === 1 && node.tagName.toUpperCase() === 'BR') {
          const text = current.join('').trim();
          if (text) parts.push(text);
          current = [];
        } else if (node.nodeType === 3) {
          current.push(node.textContent || '');
        } else if (node.nodeType === 1) {
          current.push(node.textContent || '');
        }
      }
      const last = current.join('').trim();
      if (last) parts.push(last);
      return parts;
    }

    // Finds the character offset of targetImg within container's innerText
    // Uses Range.getBoundingClientRect + caretRangeFromPoint to locate the img's position
    function findTextOffset(container, targetImg) {
      try {
        const doc = container.ownerDocument;
        const range = doc.createRange();
        // Get bounding rect of the target image
        const rects = targetImg.getBoundingClientRect();
        if (!rects || rects.length === 0) return 0;
        const x = rects.left + rects.width / 2;
        const y = rects.top + rects.height / 2;
        // Use caretRangeFromPoint to find what text is at the img's position
        const pt = doc.caretRangeFromPoint ? doc.caretRangeFromPoint(x, y) : null;
        if (!pt || !pt.startContainer) return 0;
        // Compute offset: sum of textContent lengths of all nodes before pt.startContainer
        let offset = 0;
        const walker = doc.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (node === pt.startContainer) {
            offset += pt.startOffset;
            break;
          }
          offset += node.textContent.length;
        }
        return offset;
      } catch (e) {
        return 0;
      }
    }

    function walk(node) {
      if (node.nodeType === 3) {
        // Text node
        const text = clean(node.textContent || '');
        if (text) contentItems.push({ type: 'text', value: text });
      } else if (node.nodeType === 1) {
        const tag = node.tagName.toUpperCase();
        if (tag === 'IMG') {
          const src = (node.getAttribute('src') || node.getAttribute('data-src') || '').trim();
          const alt = clean(node.getAttribute('alt') || node.getAttribute('title') || '');
          const isIncluded = imgIncludePatterns.some((p) => p.test(src));
          const isExcluded = imgExcludePatterns.some((p) => p.test(src));
          if (src && isIncluded && !isExcluded) {
            contentItems.push({ type: 'image', src, alt });
          }
          return; // don't recurse into img children
        }
        if (['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(tag)) return;
        // For block-level elements, push their full text as one unit
        if (BLOCK_TAGS.has(tag)) {
          // SPECIAL CASE: structural article containers (HBR Taiwan .container-xl.articleSet)
          // These contain a MIX of: audio-player UI, cover images, author bio,
          // and the actual article body as direct children — depth-first walk gives wrong order.
          // Strategy: use innerText (respects CSS display order) for text ordering,
          // then map images back by finding their character offset in innerText.
          const cls = (node.getAttribute('class') || '');
          const isStructuralContainer = cls.includes('articleSet') || cls.includes('container-xl');
          if ((tag === 'DIV' || tag === 'SECTION') && isStructuralContainer) {
            // Walk each direct child node in tree order — images and text blocks are
            // naturally interleaved at the container level, matching visual reading order.
            // For child DIVs/SECTIONs (like .articleCenter), walk their children recursively
            // in tree order so images inside them are interleaved with text at the right spots.
            Array.from(node.childNodes).forEach((child) => {
              if (child.nodeType === 3) {
                const text = stripNoiseFromText(child.textContent || '');
                if (text) contentItems.push({ type: 'text', value: text });
              } else if (child.nodeType === 1) {
                const childTag = child.tagName.toUpperCase();
                if (childTag === 'IMG') {
                  const src = (child.getAttribute('src') || child.getAttribute('data-src') || '').trim();
                  const alt = clean(child.getAttribute('alt') || child.getAttribute('title') || '');
                  const isIncluded = imgIncludePatterns.some((p) => p.test(src));
                  const isExcluded = imgExcludePatterns.some((p) => p.test(src));
                  if (src && isIncluded && !isExcluded) {
                    contentItems.push({ type: 'image', src, alt });
                  } else {
                  }
                } else if (!['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(childTag)) {
                  // For child DIVs/SECTIONs, walk their children in tree order directly here
                  // (don't call walk() on them as block units, which would collapse innerText)
                  if (childTag === 'DIV' || childTag === 'SECTION') {
                    Array.from(child.childNodes).forEach((grandchild) => {
                      if (grandchild.nodeType === 3) {
                        const text = stripNoiseFromText(grandchild.textContent || '');
                        if (text) contentItems.push({ type: 'text', value: text });
                      } else if (grandchild.nodeType === 1) {
                        const gcTag = grandchild.tagName.toUpperCase();
                        if (gcTag === 'IMG') {
                          const src = (grandchild.getAttribute('src') || grandchild.getAttribute('data-src') || '').trim();
                          const alt = clean(grandchild.getAttribute('alt') || grandchild.getAttribute('title') || '');
                          const isIncluded = imgIncludePatterns.some((p) => p.test(src));
                          const isExcluded = imgExcludePatterns.some((p) => p.test(src));
                          if (src && isIncluded && !isExcluded) {
                            contentItems.push({ type: 'image', src, alt });
                          }
                        } else if (!['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(gcTag)) {
                          // Deep walk for non-block elements inside child divs
                          walk(grandchild);
                        }
                      }
                    });
                  } else {
                    // SPECIAL: .articleCtn and .fixedInfo are article body sub-containers
                    // that hold both images and text as their own children — tree-walk them directly
                    const subCls = child.getAttribute('class') || '';
                    if (subCls.includes('articleCtn') || subCls.includes('fixedInfo')) {
                      Array.from(child.childNodes).forEach((gc) => {
                        if (gc.nodeType === 3) {
                          const text = stripNoiseFromText(gc.textContent || '');
                          if (text) contentItems.push({ type: 'text', value: text });
                        } else if (gc.nodeType === 1) {
                          const gcTag = gc.tagName.toUpperCase();
                          if (gcTag === 'IMG') {
                            const src = (gc.getAttribute('src') || gc.getAttribute('data-src') || '').trim();
                            const alt = clean(gc.getAttribute('alt') || gc.getAttribute('title') || '');
                            const isIncluded = imgIncludePatterns.some((p) => p.test(src));
                            const isExcluded = imgExcludePatterns.some((p) => p.test(src));
                            if (src && isIncluded && !isExcluded) {
                              contentItems.push({ type: 'image', src, alt });
                            }
                          } else if (!['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(gcTag)) {
                            walk(gc);
                          }
                        }
                      });
                    } else {
                      // Non-block child: recurse normally
                      walk(child);
                    }
                  }
                }
              }
            });
            return;
          }
          // SPECIAL CASE: .articleCenter div — the main article body container
          // Contains all article body sub-containers (.articleCtn, .fixedInfo, etc.)
          // and their nested structure.
          // Strategy: collect all images in reading order using querySelectorAll,
          // then interleave them with text chunks using TreeWalker character offsets.
          const artCenterCls = (node.getAttribute('class') || '');
          if (tag === 'DIV' && artCenterCls.includes('articleCenter')) {
            // Collect ALL images within articleCenter (not just direct children)
            const allImgs = Array.from(node.querySelectorAll('img'));
            // Sort images by their TreeWalker document position
            const sortedImgs = [];
            const imgWalker = node.ownerDocument.createTreeWalker(node, NodeFilter.SHOW_ELEMENT, {
              acceptNode: (n) => n.tagName.toUpperCase() === 'IMG' ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
            });
            let wn;
            while ((wn = imgWalker.nextNode())) sortedImgs.push(wn);
            // Build text + image interleaving using character offsets from innerText
            const fullText = node.innerText || '';
            const textToImgOffsets = []; // {imgIndex, charOffset}
            for (const img of sortedImgs) {
              // Find char offset of img in fullText using a boundary comparison approach
              // We use comparePoint: find where img appears in the text by trying to locate it
              // Use Range.getBoundingClientRect to find visual position, then match to text
              // For simplicity: use TreeWalker text nodes to accumulate offset
              let offset = 0;
              let found = false;
              const textWalker = node.ownerDocument.createTreeWalker(node, NodeFilter.SHOW_TEXT, null);
              let txtNode;
              while ((txtNode = textWalker.nextNode())) {
                const nodeEnd = offset + txtNode.textContent.length;
                // Does this text node's range contain the img?
                // We use comparePoint: range.comparePoint(node, offset)
                try {
                  const r = node.ownerDocument.createRange();
                  r.selectNode(txtNode);
                  if (r.comparePoint(img, 0) === 0) {
                    // img is AT the start of this text node
                    const r2 = node.ownerDocument.createRange();
                    r2.setStartBefore(txtNode);
                    const off = r2.toString().length;
                    textToImgOffsets.push({ img, charOffset: off });
                    found = true;
                    break;
                  }
                } catch(e) {}
                offset = nodeEnd;
              }
              if (!found) {
                // Fallback: put at end
                textToImgOffsets.push({ img, charOffset: fullText.length });
              }
            }
            textToImgOffsets.sort((a, b) => a.charOffset - b.charOffset);
            // Now split fullText at each img offset and interleave
            let lastOffset = 0;
            for (const { img, charOffset } of textToImgOffsets) {
              if (charOffset > lastOffset) {
                const textChunk = stripNoiseFromText(fullText.slice(lastOffset, charOffset));
                if (textChunk) contentItems.push({ type: 'text', value: textChunk });
              }
              const src = (img.getAttribute('src') || img.getAttribute('data-src') || '').trim();
              const alt = clean(img.getAttribute('alt') || img.getAttribute('title') || '');
              const isIncluded = imgIncludePatterns.some((p) => p.test(src));
              const isExcluded = imgExcludePatterns.some((p) => p.test(src));
              if (src && isIncluded && !isExcluded) {
                contentItems.push({ type: 'image', src, alt });
              }
              lastOffset = charOffset;
            }
            // Final text chunk after last image
            if (lastOffset < fullText.length) {
              const textChunk = stripNoiseFromText(fullText.slice(lastOffset));
              if (textChunk) contentItems.push({ type: 'text', value: textChunk });
            }
            return;
          }
          // SPECIAL CASE: DIV/SECTION with P children — walk each P individually
          // to preserve paragraph structure (clean() collapses \n inside text)
          if ((tag === 'DIV' || tag === 'SECTION') && node.querySelector('p')) {
            Array.from(node.childNodes).forEach(walk);
            return;
          }
          // SPECIAL CASE: block elements with <br> separators — split on BR
          const brSeparated = tag === 'DIV' || tag === 'SECTION' || tag === 'P';
          if (brSeparated) {
            // Split text content by <br> tags to get individual paragraphs/chunks
            const parts = splitByBr(node);
            for (const part of parts) {
              const text = clean(part);
              if (!text) continue;
              // Infer heading from bold/strong text
              const boldText = node.querySelector('strong, b, h1, h2, h3, h4');
              const isHeading = boldText && node.textContent.trim() === boldText.textContent.trim();
              if (isHeading) {
                contentItems.push({ type: 'text', value: `## ${clean(boldText.textContent)}` });
              } else {
                contentItems.push({ type: 'text', value: text });
              }
            }
            return;
          }
          const text = clean(node.textContent || '');
          if (text) {
            if (/^H[1-4]$/i.test(tag)) contentItems.push({ type: 'text', value: `## ${text}` });
            else if (tag === 'LI') contentItems.push({ type: 'text', value: `- ${text}` });
            else contentItems.push({ type: 'text', value: text });
          }
        } else {
          // Recurse into non-block children (inline elements)
          Array.from(node.childNodes).forEach(walk);
        }
      }
    }

    Array.from(container.childNodes).forEach(walk);

    if (contentItems.length === 0) {
      push(container.textContent || '');
    }

    // Serialize contentItems to body string, injecting {{IMG:N}} at image positions
    // Only include images that are in the images[] deduplication list
    const imageIndexMap = new Map(); // src -> index in images[]
    images.forEach((img, i) => imageIndexMap.set(img.src, i));

    const bodyParts = [];
    let imgCounter = 0;
    for (const item of contentItems) {
      if (item.type === 'image') {
        // Map this image src back to its images[] index
        const imgIdx = imageIndexMap.get(item.src);
        if (imgIdx !== undefined) {
          bodyParts.push(`{{IMG:${imgIdx}}}`);
          imgCounter++;
        }
      } else {
        bodyParts.push(item.value);
      }
    }

    const bodyContent = bodyParts.join('\n\n');

    return {
      title,
      description,
      published,
      authors: authorNames,
      body: bodyContent,
      _origBody: bodyContent,
      images,
      contentItems,
      pageType: fallbackPageType,
      pageTitle: clean(document.title),
      htmlLang: document.documentElement.lang || '',
      pathname: location.pathname,
      ogUrl: attrOf('meta[property="og:url"]', 'content'),

    };
  }, { url, fallbackPageType: detectPageTypeFromUrl(url) });
}

function postProcessExtract(extracted, url) {
  const title = cleanInlineText(extracted.title || extracted.pageTitle || 'HBR Taiwan')
    .replace(/\s*[|｜]\s*哈佛商業評論.*$/, '').trim();
  const rawLines = String(extracted.body || '').split(/\n+/);
  const bodyLines = [];
  for (const line of rawLines) {
    const cleaned = cleanInlineText(line).replace(/^##\s*##\s*/, '## ');
    if (!cleaned) continue;
    // Strip list/heading prefixes for title duplicate check
    const strippedForTitle = cleaned.replace(/^[-*]\s+/, '').replace(/^#+\s*/, '');
    if (strippedForTitle === title) continue;
    if (isNoiseLine(cleaned)) continue;
    if (bodyLines[bodyLines.length - 1] === cleaned) continue;
    bodyLines.push(cleaned);
  }

  let body = bodyLines.join('\n\n').trim();

  // Split off author bio + related-articles sections
  // These appear after the translator note "（林俊宏譯）" or author ## headings
  // Strategy: find the LAST occurrence of key end-markers and trim everything after
  const endMarkers = [
    '（林俊宏譯）',
    // Specific author headings (H2 style)
    '## 拉斯穆斯．霍加德 Rasmus Hougaard',
    '## 拉斯穆斯．霍加德',
    '## 賈桂琳．卡特',
    // Author bio section headings (## name without heading prefix in text)
    '本文作者',
    '本文作者：',
    '作者簡介',
    // Structural end markers
    '## 本篇文章主題',
    '## 更多關聯主題',
    '本篇文章主題',
    '更多關聯主題',
    // Generic: lines that look like author bylines (name + role/affiliation, standalone)
    // Matches: "茱莉．貝達 Julie Bedard 波士頓顧問公司董事總經理暨合夥人"
    // These appear as standalone lines in the bio section at the article bottom
    // Pattern: Chinese name + Western name + company/institution (no surrounding prose context)
  ];

  let earliestMarkerIndex = -1;
  let earliestMarker = '';
  for (const marker of endMarkers) {
    const idx = body.lastIndexOf(marker);
    if (idx !== -1 && (earliestMarkerIndex === -1 || idx < earliestMarkerIndex)) {
      earliestMarkerIndex = idx;
      earliestMarker = marker;
    }
  }

  if (earliestMarkerIndex !== -1) {
    body = body.slice(0, earliestMarkerIndex).trim();
  }

  const description = cleanInlineText(extracted.description || '');
  if (!body || body.length < 180) {
    const summaryLines = [
      `來源頁型：${detectPageTypeFromUrl(url)}`,
      description ? `摘要：${description}` : '',
      body,
    ].filter(Boolean);
    body = summaryLines.join('\n\n').trim();
  }

  // Clean authors: extract just the names, then deduplicate by first token
  const rawAuthors = extracted.authors || [];
  const cleanedAuthors = rawAuthors.map(cleanAuthor).filter((name) => name);
  // Deduplicate: keep first occurrence of each first-name-token
  const seenFirstToken = new Set();
  const authors = cleanedAuthors.filter((name) => {
    const firstToken = name.split(/[\s\n]/)[0].toLowerCase();
    if (seenFirstToken.has(firstToken)) return false;
    seenFirstToken.add(firstToken);
    return true;
  });

  const dateMatch = String(extracted.published || '').match(/\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/);
  // Fallback: scan body text for date if not found in meta
  const bodyDateMatch = !dateMatch ? String(extracted.body || '').match(/\b(\d{4})[\/.](\d{1,2})[\/.](\d{1,2})\b/) : null;
  const date_published = dateMatch
    ? dateMatch[0].replace(/[/.]/g, '-')
    : (bodyDateMatch ? `${bodyDateMatch[1]}-${bodyDateMatch[2].padStart(2,'0')}-${bodyDateMatch[3].padStart(2,'0')}` : '');

  const pageType = detectPageTypeFromUrl(url);
  const tags = uniqueNonEmpty(['HBR', pageType !== 'article' ? pageType : '']);

  // ─── Content Integrity Check ────────────────────────────────────────────────
  // Detect if article content appears truncated (e.g., by paywall / expired session)
  // Short-form content (Q&A interviews, Life's Work, etc.) may be genuinely short —
  // only flag as truncated if there's a genuine cut-off signal, not just low word count.
  const CONTENT_MIN_CHARS = 3000;   // minimum for full-length articles
  const CONTENT_ABSOLUTE_MIN = 1200; // absolute minimum for any published content
  const CONTENT_MIN_PARAS = 5;      // minimum substantive paragraphs

  // Signals that article ended at a natural structural boundary (not cut off)
  const naturalEndingPatterns = [
    /\([\u4e00-\u9fff]{2,4}譯[）)]$/,
    /^\d{4}年\d{1,2}月/m,
    /^##\s[\u4e00-\u9fff]/m,
  ];
  const hasNaturalEnding = naturalEndingPatterns.some((p) => p.test(body.trim()));

  const paragraphs = body.split(/\n{2,}/).filter((p) => p.trim().length > 50);
  const endsWithEllipsis = /[\u2026\u22EF…]{1,3}$/.test(body.trim());
  const hasSentenceEnding = /[。！？？」』]$/.test(body.trim());
  const isShort = body.length < CONTENT_MIN_CHARS;
  const isSparse = paragraphs.length < CONTENT_MIN_PARAS;
  const isTooShort = body.length < CONTENT_ABSOLUTE_MIN;

  // Truncated if: genuinely too short (no natural ending, no sentence end, AND short)
  // OR ends with ellipsis
  // OR suspiciously few paragraphs
  const isTruncated = endsWithEllipsis
    || (isTooShort && !hasNaturalEnding && !hasSentenceEnding)
    || (isShort && isSparse && !hasNaturalEnding && !hasSentenceEnding);

  const integrityWarning = isTruncated
    ? `⚠️ 內容可能不完整（僅 ${body.length} 字，${paragraphs.length} 段）——可能為 Paywall 截斷或登入階段已過期，建議重新登入 HBR Taiwan 後重新匯入。`
    : '';

  // ─── Inject images at their original reading-order positions ───────────────────
  // We use the _origBody (the original bodyContent with {{IMG:N}} markers) to derive
  // processedImages, and then use the rebuilt body (with inline image placeholders) for bodyWithImages.
  // Fix: use _origBody (original body with {{IMG:N}} markers) to compute processedImages
  let processedImages = new Set(); // track which images were injected inline
  // Heuristic: images[0] is the cover (prepended), images[1+] are inline.
  const allImages = extracted.images || [];
  for (let i = 1; i < allImages.length; i++) {
    processedImages.add(i);
  }

  // Inject inline image markers at the CORRECT position in the body:
  // after the first real article paragraph (skip audio player UI noise at the top).
  // We find the position by looking for the first substantial Chinese text block.
  let bodyWithImages = body;
  const inlineMarkers = [];
  for (let i = 1; i < allImages.length; i++) {
    inlineMarkers.push(`{{IMG_PLACEHOLDER:${i}}}`);
  }
  if (inlineMarkers.length > 0 && bodyWithImages.length > 0) {
    // Find the first substantial text (>50 chars, contains Chinese)
    const lines = bodyWithImages.split(/\n+/);
    let injectAfter = 0; // default: top of body
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      // Skip lines that look like audio player UI or noise
      if (line.length > 40 && /[\u4e00-\u9fff]/.test(line)) {
        injectAfter = i;
        break;
      }
    }
    // Inject markers after the first substantial paragraph
    const bodyLines = bodyWithImages.split(/\n{2,}/);
    if (injectAfter < bodyLines.length) {
      const before = bodyLines.slice(0, injectAfter + 1).join('\n\n');
      const after = bodyLines.slice(injectAfter + 1).join('\n\n');
      bodyWithImages = before + '\n\n' + inlineMarkers.join('\n\n') + (after ? '\n\n' + after : '');
    } else {
      bodyWithImages = inlineMarkers.join('\n\n') + '\n\n' + bodyWithImages;
    }
  }


  const status = isTruncated ? 'partial' : 'complete';
  const bodyWithWarning = integrityWarning
    ? `> ${integrityWarning}\n\n${bodyWithImages}`
    : bodyWithImages;

  return {
    title,
    title_en: '',
    source: normalizeUrl(url),
    publisher,
    authors,
    date_published,
    date_saved: todayLocal(),
    tags,
    domains: [],
    status,
    page_type: pageType,
    body: bodyWithWarning,
    images: extracted.images || [],
    inlineImageIndices: [...processedImages], // indices of images already injected into body
  };
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function main() {
  const { urls: argvUrls, dryRun, probeOnly, useCdp, vault, profile } = parseArgs(process.argv.slice(2));
  const { urls, inputWarnings } = await collectUrls(argvUrls);

  if (!urls.length) {
    console.error(usage.trim());
    process.exit(1);
  }

  // ─── Pre-flight probe (only when NOT using CDP) ─────────────────────────────
  // CDP mode skips probe — it connects to an already-running Chrome where session state is unknown
  // In CDP mode, content quality is validated per-article (truncated → warning + partial status)
  if (!useCdp) {
    const shouldProbe = probeOnly || urls.length >= 3;
    if (shouldProbe) {
      console.error(`[probe] Checking HBR Taiwan session (${urls.length} articles queued)...`);
      const probeResult = await probeSession(profile, urls[0]);
      if (!probeResult.ok) {
        console.error(`[probe] ❌ Session invalid — ${probeResult.reason}`);
        console.error('[probe] Please log in to HBR Taiwan in Chrome, then re-run the import.');
        process.exit(1);
      }
      console.error(`[probe] ✅ Session OK (${probeResult.chars} chars fetched, sufficient content)`);
      if (probeOnly) {
        console.error('[probe] Exiting (--probe mode). Remove --probe to start the full import.');
        process.exit(0);
      }
    }
  }

  const { chromium } = await loadPlaywright();
  await ensureDir(vault);
  const existingSourceMap = await buildExistingSourceMap(vault);

  // Launch browser: CDP mode connects to existing Chrome; otherwise launches fresh
  let browser;
  if (useCdp) {
    browser = await chromium.connectOverCDP('http://localhost:9222');
  } else {
    browser = await chromium.launchPersistentContext(profile, {
      headless: true,
      viewport: { width: 1440, height: 2200 },
    });
  }

  const summary = {
    success: [],
    failed: [],
    warnings: [...inputWarnings],
  };

  try {
    // CDP: browser.contexts()[0].pages(); normal: browser.pages()
    const ctx = useCdp ? (browser.contexts ? browser.contexts()[0] : browser) : browser;
    const page = (ctx.pages && ctx.pages()[0]) || (ctx.newPage ? await ctx.newPage() : browser.newPage());
    if (!page) throw new Error('Could not get or create page from browser context');

    for (const url of urls) {
      try {
        const extracted = await extractPage(page, url);
        const note = postProcessExtract(extracted, url);

        // Determine article folder and images folder
        const articleSlug = slugifyFilename(note.title);
        const articleFolder = path.join(vault, articleSlug);
        const imagesFolder = path.join(articleFolder, 'images');

        // Determine output .md path — always put it inside articleFolder alongside images/
        const existingPath = existingSourceMap.get(note.source);
        const mdFileName = `${articleSlug}.md`;
        // Use articleFolder for both .md and images/ so they stay together
        const outputMdPath = path.join(articleFolder, mdFileName);

        // Download images if not dry-run
        const imageMap = new Map(); // originalUrl -> localBasename
        if (!dryRun && note.images.length > 0) {
          await ensureDir(imagesFolder);
          for (let i = 0; i < note.images.length; i++) {
            const { src, alt } = note.images[i];
            if (!src) continue;
            const ext = (src.match(/\.(jpe?g|png|gif|webp|avif)/i) || ['.jpg'])[0].toLowerCase();
            const localName = `fig${i + 1}${ext}`;
            const localPath = path.join(imagesFolder, localName);
            const downloaded = await downloadImage(src, localPath);
            if (downloaded) {
              imageMap.set(src, { localName, alt });
            } else {
              summary.warnings.push(`Failed to download image: ${src}`);
            }
          }
        }

        // Replace image URLs in body with local paths (Obsidian markdown image syntax)
        // 1. Replace {{IMG_PLACEHOLDER:N}} with actual local path (images at their original reading-order position)
        // 2. Prepend any images NOT already injected inline (cover images that appear outside content flow)
        let body = note.body;
        if (imageMap.size > 0) {
          // Step 1: resolve {{IMG_PLACEHOLDER:N}} → local markdown image
          body = body.replace(/\{\{IMG_PLACEHOLDER:(\d+)\}\}/g, (match, idxStr) => {
            const idx = parseInt(idxStr, 10);
            const imgList = note.images || [];
            if (idx < 0 || idx >= imgList.length) return '';
            const { src, alt } = imgList[idx];
            const mapped = imageMap.get(src);
            if (!mapped) return '';
            const caption = alt ? `*${alt}*` : '';
            return `![](images/${mapped.localName})${caption ? ' ' + caption : ''}`;
          });

          // Step 2: prepend images that were NOT in the reading-order flow (e.g., cover before title)
          const inlineIndices = new Set(note.inlineImageIndices || []);
          const prependedBlocks = [];
          for (let i = 0; i < note.images.length; i++) {
            if (inlineIndices.has(i)) continue;
            const { src, alt } = note.images[i];
            const mapped = imageMap.get(src);
            if (!mapped) continue;
            const caption = alt ? `*${alt}*` : '';
            prependedBlocks.push(`![](images/${mapped.localName})${caption ? ' ' + caption : ''}`);
          }
          if (prependedBlocks.length > 0) {
            body = prependedBlocks.join('\n') + '\n\n' + body;
          }
        }

        const noteWithImages = { ...note, body };

        const markdown = composeNote(noteWithImages);
        if (!dryRun) {
          await ensureDir(path.dirname(outputMdPath));
          await fs.writeFile(outputMdPath, markdown, 'utf8');
          existingSourceMap.set(note.source, outputMdPath);
        }

        const imagesDownloaded = imageMap.size;
        summary.success.push({
          url: note.source,
          file: outputMdPath,
          pageType: note.page_type,
          overwritten: Boolean(existingPath),
          imagesDownloaded,
          status: note.status,
          title: note.title,
        });
      } catch (error) {
        summary.failed.push({ url, error: error.message });
      }
    }
  } finally {
    // CDP connections use disconnect(); launched browsers use close()
    if (useCdp && typeof browser.disconnect === 'function') {
      await browser.disconnect().catch(() => {});
    } else {
      await browser.close().catch(() => {});
    }
  }

  const lines = [];
  const partialCount = summary.success.filter((s) => s.status === 'partial').length;
  lines.push(
    `HBR import summary: success ${summary.success.length}, failed ${summary.failed.length}${partialCount ? `, partial ${partialCount}` : ''}`
  );
  if (summary.warnings.length) {
    lines.push('Warnings:');
    for (const warning of summary.warnings) lines.push(`- ${warning}`);
  }
  if (summary.success.length) {
    lines.push('Written files:');
    for (const item of summary.success) {
      const truncFlag = item.status === 'partial' ? ' ⚠️ PARTIAL' : '';
      lines.push(
        `- [${item.pageType}]${truncFlag} ${item.file}${item.overwritten ? ' (overwritten)' : ''} (${item.imagesDownloaded} images)`
      );
    }
  }
  if (summary.failed.length) {
    lines.push('Failures:');
    for (const item of summary.failed) lines.push(`- ${item.url}: ${item.error}`);
  }
  if (partialCount && !probeOnly) {
    lines.push('');
    lines.push(`⚠️  ${partialCount} article(s) are partial — login session may have expired. See ⚠️ flags above.`);
  }

  console.log(lines.join('\n'));
  if (summary.failed.length) process.exitCode = 2;
  if (partialCount) process.exitCode = 2; // partial content also earns non-zero exit
}

main().catch((error) => {
  console.error(error.message || String(error));
  process.exit(1);
});
