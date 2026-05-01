#!/usr/bin/env python3
"""
regen_summary.py — 從 chunk 快取重新生成摘要（不重新轉錄）

Usage:
  python regen_summary.py --chunk-hash <hash> \
    --course-name <課程名> \
    --date 2026-04-11 \
    --professor <教授> \
    --template D2 \
    --final-model anthropic/claude-sonnet-4-6 \
    --notion-page <page_id> \
    [--obsidian-path <path>]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

from summary_prompts import (
    select_template, build_system_prompt, build_chunk_prompt, build_reduce_prompt,
    TEMPLATE_NAMES, apply_course_specific_summary_flags,
)
from notion_upload import overwrite_page

CONFIG = {
    "cache_dir": Path.home() / "whisperx-outputs" / "cache",
    "output_dir": Path.home() / "whisperx-outputs",
}

CHUNK_MINUTES = 30  # 每個 chunk 是 30 分鐘

def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or '').strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'on'}


ALLOW_GOOGLE_CHUNK_FALLBACK = _env_flag('LECTURE_TRANSCRIBE_ALLOW_GOOGLE_CHUNK_FALLBACK', False)
ALLOW_GOOGLE_FINAL_FALLBACK = _env_flag('LECTURE_TRANSCRIBE_ALLOW_GOOGLE_FINAL_FALLBACK', False)


def _build_chunk_fallback_chain() -> list[str]:
    chain = [
        "google-ai/gemma-4-31b-it",
        "openai-codex/gpt-5.4",
    ]
    if ALLOW_GOOGLE_CHUNK_FALLBACK:
        chain.append("google/gemini-2.5-flash")
    return chain


def _build_final_fallback_chain() -> list[str]:
    chain = [
        "minimax-portal/MiniMax-M2.7",
    ]
    if ALLOW_GOOGLE_FINAL_FALLBACK:
        chain.append("google/gemini-3-pro-preview")
    return chain


LLM_FINAL_FALLBACK_CHAIN = _build_final_fallback_chain()
LLM_CHUNK_FALLBACK_CHAIN = _build_chunk_fallback_chain()


def _append_proc_warning(proc: dict, message: str) -> None:
    warnings = proc.setdefault('llm_warnings', [])
    if message not in warnings:
        warnings.append(message)


def _fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def load_chunks_from_cache(chunk_hash: str) -> tuple[list, float]:
    """Load all chunk_<hash>_N.json and reconstruct segments with time offsets."""
    cache_dir = CONFIG["cache_dir"]
    chunks = sorted(cache_dir.glob(f"chunk_{chunk_hash}_*.json"),
                    key=lambda p: int(p.stem.rsplit("_", 1)[-1]))
    if not chunks:
        raise FileNotFoundError(f"No chunk files found for hash: {chunk_hash}")
    
    all_segments = []
    total_duration = 0.0
    
    for i, chunk_path in enumerate(chunks):
        data = json.loads(chunk_path.read_text(encoding="utf-8"))
        segs = data.get("segments", [])
        chunk_dur = data.get("duration_sec", CHUNK_MINUTES * 60)
        offset = i * CHUNK_MINUTES * 60
        
        for seg in segs:
            s = dict(seg)
            s["start"] = s.get("start", 0) + offset
            s["end"] = s.get("end", 0) + offset
            all_segments.append(s)
        
        total_duration = max(total_duration, offset + chunk_dur)
        logger.info(f"  chunk {i}: {len(segs)} segs, dur={chunk_dur:.0f}s, offset={offset:.0f}s")
    
    logger.info(f"Total: {len(all_segments)} segments, {total_duration:.0f}s")
    return all_segments, total_duration


def build_transcript_plain(segments, speakers=None):
    lines = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        ts = _fmt_ts(seg.get("start", 0))
        spk = seg.get("speaker", "")
        if spk and speakers and spk in speakers:
            disp = speakers[spk].get("display_name", spk)
            lines.append(f"[{ts}] {disp}: {text}")
        else:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _chunk_segments_for_llm(segments, speakers, max_chars=12000, max_minutes=12):
    """Split segments into LLM-size chunks."""
    chunks = []
    cur_segs = []
    cur_chars = 0
    
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        cur_segs.append(seg)
        cur_chars += len(text) + 20
        
        # Check time span
        if cur_segs:
            span_min = (cur_segs[-1].get("start", 0) - cur_segs[0].get("start", 0)) / 60
        else:
            span_min = 0
        
        if cur_chars >= max_chars or span_min >= max_minutes:
            if cur_segs:
                t0 = _fmt_ts(cur_segs[0].get("start", 0))
                t1 = _fmt_ts(cur_segs[-1].get("end", cur_segs[-1].get("start", 0)))
                lines = []
                for s in cur_segs:
                    t = s.get("text", "").strip()
                    if t:
                        spk = s.get("speaker", "")
                        if spk and speakers and spk in speakers:
                            disp = speakers[spk].get("display_name", spk)
                            lines.append(f"[{_fmt_ts(s.get('start',0))}] {disp}: {t}")
                        else:
                            lines.append(f"[{_fmt_ts(s.get('start',0))}] {t}")
                chunks.append({"label": f"{t0}~{t1}", "text": "\n".join(lines)})
                cur_segs = []
                cur_chars = 0
    
    # remainder
    if cur_segs:
        t0 = _fmt_ts(cur_segs[0].get("start", 0))
        t1 = _fmt_ts(cur_segs[-1].get("end", cur_segs[-1].get("start", 0)))
        lines = []
        for s in cur_segs:
            t = s.get("text", "").strip()
            if t:
                spk = s.get("speaker", "")
                if spk and speakers and spk in speakers:
                    disp = speakers[spk].get("display_name", spk)
                    lines.append(f"[{_fmt_ts(s.get('start',0))}] {disp}: {t}")
                else:
                    lines.append(f"[{_fmt_ts(s.get('start',0))}] {t}")
        chunks.append({"label": f"{t0}~{t1}", "text": "\n".join(lines)})
    
    return chunks


async def _call_llm(model_id, system_prompt, user_message, max_tokens=8000,
                    fallback_chain=None, proc=None, usage_bucket='final'):
    from openclaw.llm import chat_completion
    
    chain = [model_id] + list(fallback_chain or [])
    last_err = None
    for model in chain:
        for attempt in range(3):
            try:
                resp = await chat_completion(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=max_tokens,
                )
                if proc is not None:
                    usage = proc.setdefault('llm_usage', {})
                    bucket = usage.setdefault(usage_bucket, {})
                    bucket['requested_model'] = model_id
                    bucket['final_used_model'] = model
                    bucket['used_fallback'] = (model != model_id)
                    if fallback_chain:
                        bucket['fallback_chain'] = list(fallback_chain)
                    if model.startswith('google/') and model != model_id:
                        _append_proc_warning(proc, f'⚠️ {usage_bucket} 使用 Google 付費 fallback：{model}')
                logger.info(f"  LLM {usage_bucket}: {model} OK")
                return resp.get("content", "")
            except Exception as e:
                last_err = e
                logger.warning(f"  LLM {model} attempt {attempt+1} failed: {e}")
                await asyncio.sleep(1)
    raise RuntimeError(f"All models failed. Last error: {last_err}")


def _fmt_duration(sec: float) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _build_footer(metadata: dict, proc: dict) -> str:
    """Build simplified workflow footer markdown."""
    lines = ['', '---', '', '### :openclaw-dark:作業路徑說明']
    lines.append('- *來源取得：chunk 快取重新生成摘要（未重新轉錄）*')
    
    ref_sources = proc.get('reference_sources') or []
    if ref_sources:
        src_list = '、'.join(ref_sources[:6])
        lines.append(f"- *參考資料整合：納入 {len(ref_sources)} 項參考：{src_list}*")
    else:
        lines.append('- *參考資料整合：本次為單次錄音處理，未納入額外參考資料。*')
    
    lines.append('- *音訊前處理：使用 ffmpeg 進行 16kHz 單聲道正規化與 loudnorm 音量校正。*')
    
    dur_text = proc.get('audio_duration_text', '')
    seg_count = proc.get('segment_count', '')
    lines.append(f"- *逐字稿轉錄：使用 mlx-whisper 產出逐字稿{'（音訊長度約 '+dur_text+'）' if dur_text else ''}{'，共切出約 '+str(seg_count)+' 個語意片段' if seg_count else ''}。*")
    lines.append('- *快取策略：本次命中既有轉錄快取，略過重跑逐字稿。*')
    
    llm_usage = proc.get('llm_usage', {})
    chunk_usage = llm_usage.get('chunk', {})
    final_usage = llm_usage.get('final', {})
    chunk_count = proc.get('chunk_count', '多')
    chunk_model = proc.get('chunk_model', '')
    final_model = proc.get('final_model', '')
    
    lines.append(f"- *摘要生成：長音檔模式，先分成 {chunk_count} 段做分段重點整理，再由主摘要模型整併。（重新生成）*")
    lines.append(f"  - *Chunk 指定模型：{chunk_model}*")
    if chunk_usage.get('final_used_model'):
        lines.append(f"  - *Chunk 實際成功模型：{chunk_usage['final_used_model']}*")
    if not _env_flag('LECTURE_TRANSCRIBE_ALLOW_GOOGLE_DIRECT_FALLBACK', False):
        lines.append('  - *Guardrail：Gemini direct fallback 預設停用；regen_summary 僅走 OpenClaw routing。*')
    lines.append(f"  - *Final 指定模型：{final_model}*")
    if final_usage.get('final_used_model'):
        lines.append(f"  - *Final 實際成功模型：{final_usage['final_used_model']}*")
    for warning in proc.get('llm_warnings', []):
        lines.append(f"  - *{warning}*")
    lines.append('- *說話者處理：未啟用說話者分辨 / speaker diarization（以穩定與速度優先）。*')
    
    total_sec = proc.get('total_elapsed_sec', 0)
    lines.append(f"- *耗時：重新生成摘要約 {int(total_sec)} 秒。*")
    lines.append('- *上傳歸檔：同步寫入 :notion: Notion 課堂摘要庫 ＋ :obsidian-color: Obsidian 本地 Vault。*')
    lines.append('')
    
    course_name = metadata.get('course_name', '')
    date_str = metadata.get('date', '')
    obsidian_path = f"EMBA/02 每週課堂筆記/{course_name}/{date_str}_{course_name}.md"
    lines += [
        '> ***⚠️ 本筆記摘要為 AI Agent :openclaw-dark:調用大語言模型（LLM）自動化 Workflow 生成。依據使用者提供錄音檔、加上個人筆記及其他補充材料進行自動交叉校對完成，但仍可能存在誤解、遺漏、錯別字或表述偏差；若需正式引用、對外使用或作為決策依據，請務必加以核實。***',
        '',
        '### 🗂 Obsidian 知識庫連結',
        f'- 📓 本堂課堂筆記　{obsidian_path}',
        f'- 📚 課程主檔　[[{course_name}]]',
        '- 📅 學期總覽　[[114-2 課程總覽]]',
    ]
    
    return '\n'.join(lines)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunk-hash', required=True, help='Cache chunk hash (e.g. 4daace6fb8f9)')
    parser.add_argument('--course-name', default='全球台商個案研討')
    parser.add_argument('--date', default='2026-04-11')
    parser.add_argument('--professor', default='')
    parser.add_argument('--template', default='D2')
    parser.add_argument('--final-model', default='anthropic/claude-sonnet-4-6')
    parser.add_argument('--chunk-model', default='minimax-portal/MiniMax-M2.7')
    parser.add_argument('--notion-page', help='Notion page ID to overwrite')
    parser.add_argument('--obsidian-path', help='Obsidian note path to overwrite')
    parser.add_argument('--dry-run', action='store_true', help='Generate summary but do not upload')
    args = parser.parse_args()
    
    t0 = time.time()
    
    # 1. Load chunks
    logger.info(f"Loading chunks for hash: {args.chunk_hash}")
    segments, duration_sec = load_chunks_from_cache(args.chunk_hash)
    
    # 2. Build transcript
    plain = build_transcript_plain(segments)
    logger.info(f"Transcript: {len(plain)} chars")
    
    # 3. Set up metadata with D2 flags
    metadata = {
        'type': 'emba',
        'course_name': args.course_name,
        'professor': args.professor,
        'date': args.date,
        'template_override': args.template.upper(),
        'model_pref': args.final_model,
    }
    apply_course_specific_summary_flags(metadata, plain)
    logger.info(f"D2 flags: global_taiwan_case_mode={metadata.get('global_taiwan_case_mode')}, detailed_case_restore={metadata.get('detailed_case_restore')}")
    
    proc = {
        'audio_duration_text': _fmt_duration(duration_sec),
        'segment_count': len(segments),
        'used_cache': True,
        'used_chunking': True,
        'final_model': args.final_model,
        'chunk_model': args.chunk_model,
        'chunk_fallback_chain': LLM_CHUNK_FALLBACK_CHAIN[:],
        'final_fallback_chain': LLM_FINAL_FALLBACK_CHAIN[:],
        'llm_usage': {},
        'llm_policy': {
            'chunk_default': 'minimax-portal/MiniMax-M2.7',
            'chunk_fallback_chain': LLM_CHUNK_FALLBACK_CHAIN[:],
            'final_fallback_chain': LLM_FINAL_FALLBACK_CHAIN[:],
            'allow_google_chunk_fallback': ALLOW_GOOGLE_CHUNK_FALLBACK,
            'allow_google_final_fallback': ALLOW_GOOGLE_FINAL_FALLBACK,
            'allow_google_direct_fallback': False,
        },
    }
    
    # 4. Template routing
    tmpl = metadata['template_override']
    logger.info(f"Template: {tmpl} ({TEMPLATE_NAMES.get(tmpl, tmpl)})")
    
    # 5. Chunk summarization
    chunks = _chunk_segments_for_llm(segments, None, max_chars=12000, max_minutes=12)
    proc['chunk_count'] = len(chunks)
    logger.info(f"Split into {len(chunks)} LLM chunks")
    
    tmpl_sys, metadata_block, glossary_md = build_system_prompt(tmpl, plain, metadata, {})
    
    import asyncio
    sem = asyncio.Semaphore(3)
    
    async def _summarize_one(i, ch):
        label = f"{i}/{len(chunks)} {ch['label']}"
        sys_c, usr_c = build_chunk_prompt(ch["text"], label, metadata, {})
        async with sem:
            note = await _call_llm(
                args.chunk_model,
                sys_c,
                usr_c,
                max_tokens=1200,
                fallback_chain=LLM_CHUNK_FALLBACK_CHAIN,
                proc=proc,
                usage_bucket='chunk',
            )
        logger.info(f"  chunk {i}/{len(chunks)} done")
        return i, label, note
    
    tasks = [asyncio.create_task(_summarize_one(i, ch)) for i, ch in enumerate(chunks, 1)]
    chunk_notes = [None] * len(chunks)
    for fut in asyncio.as_completed(tasks):
        i, label, note = await fut
        chunk_notes[i-1] = f"## {label}\n{note}"
    
    chunk_notes_md = "\n\n".join([x for x in chunk_notes if x])
    
    # 6. Final reduce
    logger.info(f"Running final reduce with {args.final_model}")
    sys_p, usr_m = build_reduce_prompt(
        tmpl_sys,
        metadata_block,
        chunk_notes_md,
        glossary_md,
        '',
        metadata=metadata,
    )
    
    summary = await _call_llm(
        args.final_model,
        sys_p,
        usr_m,
        max_tokens=6000,
        fallback_chain=LLM_FINAL_FALLBACK_CHAIN,
        proc=proc,
        usage_bucket='final',
    )
    
    proc['total_elapsed_sec'] = time.time() - t0
    
    # 7. Append footer
    footer = _build_footer(metadata, proc)
    full_md = summary.rstrip() + '\n' + footer
    
    # 8. Save to local file
    out_path = CONFIG["output_dir"] / f"{args.date}_{args.course_name}.md"
    out_path.write_text(full_md, encoding='utf-8')
    logger.info(f"Saved to: {out_path}")
    
    # 9. Update Obsidian
    obsidian_path = args.obsidian_path
    if not obsidian_path:
        vault = Path.home() / "Documents" / "小龍女知識庫"
        obsidian_path = vault / "EMBA" / "02 每週課堂筆記" / args.course_name / f"{args.date}_{args.course_name}.md"
    else:
        obsidian_path = Path(obsidian_path)
    
    # Build Obsidian version (with YAML front matter)
    frontmatter = f"""---
date: {args.date}
title: "{args.course_name}"
professor: "{args.professor}"
type: emba
tags:
  - lecture-transcribe
  - emba
---
"""
    obsidian_md = frontmatter + full_md
    obsidian_path.parent.mkdir(parents=True, exist_ok=True)
    obsidian_path.write_text(obsidian_md, encoding='utf-8')
    logger.info(f"Saved Obsidian: {obsidian_path}")
    
    if args.dry_run:
        logger.info("Dry run: skipping Notion upload")
        print("\n=== SUMMARY PREVIEW (first 500 chars) ===")
        print(summary[:500])
        return
    
    # 10. Overwrite Notion page
    if args.notion_page:
        logger.info(f"Overwriting Notion page: {args.notion_page}")
        try:
            n = overwrite_page(args.notion_page, full_md, metadata, expected_db_type='emba')
            logger.info(f"Notion: wrote {n} blocks")
        except Exception as e:
            logger.error(f"Notion overwrite failed: {e}")
            raise
    
    logger.info(f"Done! Total: {proc['total_elapsed_sec']:.0f}s")
    print(f"\n✅ 摘要重新生成完成！")
    print(f"  模型: {proc['llm_usage'].get('final', {}).get('final_used_model', args.final_model)}")
    print(f"  本地: {out_path}")
    print(f"  Obsidian: {obsidian_path}")
    if args.notion_page:
        print(f"  Notion: {args.notion_page} ✓")


if __name__ == '__main__':
    asyncio.run(main())
