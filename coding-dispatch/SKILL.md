---
name: coding-dispatch
description: "Route software engineering requests into the most cost-effective OpenClaw execution path. Use when the user asks to build, refactor, debug, review, test, or automate code; when deciding between direct read/edit work vs a spawned coding session; or when the user explicitly asks to use Claude Code, Codex, or another coding agent. Optimized for low-token operation: prefer direct edits for small work, use push-based spawned sessions for multi-step or long-running coding tasks, and avoid poll-heavy background workflows."
---

# Coding Dispatch

Route coding work by complexity, runtime, and notification needs. Optimize for low token usage and reliable completion.

## Decision tree

1. **Do it inline** when the task is small and local.
   - Good fit: one-file edits, short bug fixes, small config changes, quick reads, simple commands.
   - Default tools: `read`, `edit`, `write`, short foreground `exec`.
   - Avoid spawning a coding session for trivial fixes.

2. **Spawn a coding session** when the task is exploratory, multi-file, iterative, or likely to exceed ~2 minutes.
   - Good fit: feature work, refactors, repo-wide debugging, test repair, code review with changes, framework migration, "use Claude Code/Codex" requests.
   - Prefer `sessions_spawn` over background `exec` when the user expects a result update.
   - Use ACP harness requests through `sessions_spawn` with `runtime: "acp"`.

3. **Never use poll-heavy background monitoring as the default long-task pattern.**
   - Do not promise proactive completion from `exec background:true`.
   - Favor push-style completion via spawned sessions.

## Routing rules

### A. Small local task
Use inline work if most of these are true:
- single file or tightly scoped change
- little or no repo exploration needed
- expected runtime under ~2 minutes
- no explicit request for Claude Code / Codex / another coding harness

Deliverables:
- make the change directly
- run minimal validation if available
- report what changed, what was checked, and any follow-up risk

### B. Medium / large coding task
Use a spawned coding session if any of these are true:
- multiple files or unclear blast radius
- repo exploration is needed before editing
- iterative testing / debugging is needed
- expected runtime over ~2 minutes
- the user explicitly asks for Claude Code, Codex, Gemini CLI, or similar coding harness
- the user wants the main chat kept free while work proceeds

Default behavior:
- summarize the task into a compact implementation brief
- include success criteria, constraints, working directory, and desired validation
- spawn one coding session
- let the child session do the heavy lifting
- return a concise human summary in the main chat

## ACP harness rules

When the user explicitly asks for a coding harness such as Claude Code or Codex in chat:
- use `sessions_spawn` with `runtime: "acp"`
- on Discord, default to `thread: true` and `mode: "session"` unless the user asks otherwise
- set `agentId` explicitly
- do not emulate ACP by running local PTY wrappers when `sessions_spawn` is the correct first-class path

## Task brief template

Use this structure when spawning a coding session:

- **Goal:** what to build / fix / review
- **Context:** repo path, relevant files, framework, constraints
- **Definition of done:** concrete success criteria
- **Validation:** tests / commands / checks to run
- **Output back to main chat:**
  1. summary of changes
  2. files touched
  3. validation results
  4. open questions / risks

Keep the brief compact. Do not dump unnecessary conversation history.

## Default response pattern in main chat

Before dispatch:
- say what path you are choosing: inline vs spawned coding session
- explain why in one sentence if helpful

After completion:
- summarize result in plain language
- include whether validation passed
- surface risks or follow-ups instead of burying them

## Cost-control heuristics

- prefer direct `read`/`edit` for tiny changes
- prefer one well-scoped spawned session over many small retries
- avoid repeated status polling
- avoid stuffing the child brief with excessive history
- do not route simple reading tasks to coding agents
- if the task becomes much larger than first estimated, switch to a spawned session early

## Safety

- ask before destructive operations, external publishing, or credential changes
- keep workspace-local work bold, external actions cautious
- do not hardcode secrets or tokens into scripts
- prefer deterministic, inspectable OpenClaw-native flows over brittle glue scripts
