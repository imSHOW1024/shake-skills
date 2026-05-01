---
name: lme-browser-eval
description: OpenClaw agent tool for LME browser evaluate — wraps `openclaw browser evaluate` via exec (not Python subprocess) to avoid SIGTERM hangs in cron. Use when fetching LME chart data from within the lme-monitor pipeline, or whenever `openclaw browser evaluate` would otherwise be called from Python subprocess.run.
---

# LME Browser Eval Tool

Wrapper script that calls `openclaw browser evaluate` via shell exec (not Python subprocess).

## Why

`subprocess.run(["openclaw", "browser", "evaluate", ...])` hangs and receives SIGTERM when used inside a cron-triggered Python process. Wrapping the call in a shell script and calling it via OpenClaw agent exec sidesteps the issue entirely.

## Usage

```bash
# Via shell (agent exec path)
./lme_browser_eval.sh \
  --datasource-id <id> \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --browser-profile <profile> \
  [--target-id <target-id>]
```

**Parameters:**
- `--datasource-id` — LME chart datasource UUID
- `--start-date` — ISO date (e.g. 2026-03-24)
- `--end-date` — ISO date (e.g. 2026-03-31)
- `--browser-profile` — legacy compatibility argument only. The current OpenClaw browser CLI no longer accepts a per-command browser-profile flag, so this script ignores it for CLI routing and uses the default browser session.
- `--target-id` — optional; skip page-open if already known

**Output:** JSON (the LME chart API response) written to stdout.

**Exit codes:** 0 = success, non-zero = error (message on stderr).

## Environment

- `LME_BASE_URL` defaults to `https://www.lme.com`
- Requires `openclaw` CLI in PATH
- Requires the browser profile to already have the LME metals page open
  (or pass `--target-id` to target an existing tab)
