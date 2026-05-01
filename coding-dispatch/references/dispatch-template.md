# Coding dispatch templates

Use these compact templates when preparing a spawned coding session.

## Implementation brief

Goal:
- <what to build or fix>

Context:
- repo/workdir: <path>
- relevant files: <paths or "discover first">
- constraints: <style, deps, no-destructive-rules>

Definition of done:
- <criterion 1>
- <criterion 2>

Validation:
- <command 1>
- <command 2>

Return format:
- summary of changes
- files touched
- validation results
- remaining risks / questions

## Review / debug brief

Goal:
- identify root cause and implement the minimal safe fix

Context:
- symptoms: <error / failing test / behavior>
- likely scope: <unknown or candidate files>
- constraints: preserve existing behavior unless required

Definition of done:
- root cause explained
- fix implemented
- relevant checks pass or failure is clearly explained

Validation:
- reproduce: <command>
- verify: <command>

Return format:
- root cause
- fix summary
- files touched
- validation outcome
- next-step recommendation
