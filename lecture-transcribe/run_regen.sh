#!/bin/bash
cd /Users/openclaw/.openclaw/workspace/skills/lecture-transcribe
python3 regen_summary.py \
  --chunk-hash 4daace6fb8f9 \
  --course-name "全球台商個案研討" \
  --date 2026-04-11 \
  --professor "林震岩" \
  --template D2 \
  --final-model "anthropic/claude-sonnet-4-6" \
  --chunk-model "minimax-portal/MiniMax-M2-7" \
  --notion-page "33f35267e085816bb563fed722cb8304"
