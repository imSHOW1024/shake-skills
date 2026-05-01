#!/usr/bin/env python3
"""
VLM OCR — 用多模態視覺語言模型做 PDF OCR
比傳統 OCR（RapidOCR / PaddleOCR）品質高一到兩個等級

用法：
  python vlm_ocr.py input.pdf [--output output.md] [--model gemini-2.5-flash] [--dpi 200] [--pages 1-10]

需求：
  pip install PyMuPDF Pillow google-genai
  環境變數：GEMINI_API_KEY 或 GOOGLE_API_KEY
"""

import argparse
import io
import os
import sys
import time
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


def get_gemini_client():
    """初始化 Gemini client"""
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("需要設定 GEMINI_API_KEY 或 GOOGLE_API_KEY 環境變數")
    client = genai.Client(api_key=api_key)
    return client


def pdf_to_images(pdf_path: str, dpi: int = 200, page_range: str = None) -> list[tuple[int, bytes]]:
    """PDF 每頁轉 PNG bytes"""
    doc = fitz.open(pdf_path)
    total = doc.page_count
    
    # Parse page range
    if page_range:
        parts = page_range.split("-")
        start = max(0, int(parts[0]) - 1)
        end = min(total, int(parts[1])) if len(parts) > 1 else start + 1
    else:
        start, end = 0, total
    
    results = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    
    for i in range(start, end):
        page = doc[i]
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        results.append((i + 1, img_bytes))  # 1-indexed page number
        print(f"  📄 頁 {i+1}/{total} 已轉圖 ({len(img_bytes)//1024} KB)")
    
    doc.close()
    return results


OCR_PROMPT = """你是專業的繁體中文 OCR 轉錄員。請將這張掃描書頁的所有文字完整、準確地轉錄出來。

規則：
1. 使用台灣慣用的繁體中文（不要用簡體或大陸用字）
2. 保持原文內容完整，不要省略、摘要或改寫
3. 正文和側邊欄/重點框分開標示（側邊欄用「側邊重點：」前綴）
4. 圖片說明用「圖 X.X」格式保留
5. 人名、術語、英文保持原文
6. 如果有辨識不確定的字，根據上下文語意選擇最合理的字
7. 不要加入任何你自己的評論或補充
8. 輸出純文字，不需要 markdown 格式標記

直接輸出轉錄文字："""


def assess_page_quality(text: str, page_num: int) -> tuple[bool, str]:
    """評估 OCR 結果品質，回傳 (pass, reason)"""
    if not text or text.startswith("[OCR 失敗"):
        return False, "空白或失敗"
    
    # 1. 字數太少（正常書頁至少 100+ 字，除非是圖片頁）
    if len(text) < 50:
        return False, f"字數過少 ({len(text)})"
    
    # 2. 高頻亂碼 pattern — 傳統 OCR 常見的錯字群
    garbage_patterns = [
        r'[鷹俊棉題顥廳崽翼豬籍醫罹搐]',  # 常見 OCR 錯字
    ]
    garbage_count = 0
    for pat in garbage_patterns:
        garbage_count += len(re.findall(pat, text))
    
    # 佔比超過 2% 就可疑（正常文字這些字極少密集出現）
    garbage_ratio = garbage_count / max(len(text), 1)
    if garbage_ratio > 0.02:
        return False, f"可疑字元比例過高 ({garbage_ratio:.1%}, {garbage_count}字)"
    
    # 3. 連續非中文非英文非標點的亂碼段
    long_garbage = re.findall(r'[^\u4e00-\u9fff\u3000-\u303fA-Za-z0-9\s，。、；：「」『』（）—\-\.\,\!\?\'\"\[\]\(\)]{5,}', text)
    if len(long_garbage) > 3:
        return False, f"多段不可辨識內容 ({len(long_garbage)}段)"
    
    return True, "OK"


def ocr_page_with_vlm(client, model: str, page_num: int, img_bytes: bytes, retry: int = 3) -> str:
    """用 VLM 辨識單頁"""
    from google.genai import types
    
    for attempt in range(retry):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                            types.Part.from_text(text=OCR_PROMPT),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,  # 低溫度確保忠實轉錄
                    max_output_tokens=8192,
                )
            )
            text = response.text.strip() if response.text else ""
            if text:
                return text
            print(f"    ⚠️ 頁 {page_num} 回傳空白，重試 {attempt+1}/{retry}")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = (attempt + 1) * 15
                print(f"    ⏳ 頁 {page_num} 限流，等 {wait}s 後重試...")
                time.sleep(wait)
            else:
                print(f"    ❌ 頁 {page_num} 錯誤: {e}")
                if attempt < retry - 1:
                    time.sleep(5)
                else:
                    return f"[OCR 失敗: 頁 {page_num} — {e}]"
    
    return f"[OCR 失敗: 頁 {page_num} — 重試用盡]"


UPGRADE_MODEL = "gemini-2.5-pro"


def run_vlm_ocr(
    pdf_path: str,
    output_path: str = None,
    model: str = "gemini-2.5-flash",
    dpi: int = 200,
    page_range: str = None,
    delay: float = 1.0,
    auto_upgrade: bool = False,
) -> str:
    """主流程：PDF → 圖片 → VLM OCR → 合併文字"""
    
    pdf_path = str(Path(pdf_path).expanduser().resolve())
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"找不到 PDF: {pdf_path}")
    
    print(f"🔧 VLM OCR Pipeline")
    print(f"   PDF: {pdf_path}")
    print(f"   模型: {model}")
    print(f"   DPI: {dpi}")
    print(f"   自動升級: {'✅ 開啟' if auto_upgrade else '❌ 關閉'}")
    print()
    
    # Step 1: PDF → images
    print("📸 步驟 1/2: PDF 轉圖片...")
    pages = pdf_to_images(pdf_path, dpi=dpi, page_range=page_range)
    print(f"   共 {len(pages)} 頁\n")
    
    # Step 2: VLM OCR each page
    print("🧠 步驟 2/2: VLM 辨識中...")
    client = get_gemini_client()
    
    all_text = []
    upgrade_pages = []  # (index, page_num, img_bytes) for pages needing upgrade
    
    for idx, (page_num, img_bytes) in enumerate(pages):
        print(f"  → 頁 {page_num}...", end=" ", flush=True)
        t0 = time.time()
        text = ocr_page_with_vlm(client, model, page_num, img_bytes)
        elapsed = time.time() - t0
        char_count = len(text)
        
        # Quality check
        passed, reason = assess_page_quality(text, page_num)
        if passed:
            print(f"✅ {char_count} 字 ({elapsed:.1f}s)")
        else:
            print(f"⚠️ {char_count} 字 ({elapsed:.1f}s) — {reason}")
            if auto_upgrade:
                upgrade_pages.append((idx, page_num, img_bytes))
        
        all_text.append(text)
        
        # Rate limit courtesy delay
        if idx < len(pages) - 1 and delay > 0:
            time.sleep(delay)
    
    # Step 2.5: Auto-upgrade low quality pages with Pro
    if auto_upgrade and upgrade_pages:
        upgrade_model = UPGRADE_MODEL if model != UPGRADE_MODEL else model
        print(f"\n🔄 自動升級: {len(upgrade_pages)} 頁品質不佳，用 {upgrade_model} 重跑...")
        for list_idx, page_num, img_bytes in upgrade_pages:
            print(f"  🔁 頁 {page_num}...", end=" ", flush=True)
            t0 = time.time()
            text = ocr_page_with_vlm(client, upgrade_model, page_num, img_bytes)
            elapsed = time.time() - t0
            
            new_passed, new_reason = assess_page_quality(text, page_num)
            status = "✅" if new_passed else "⚠️ 仍不理想"
            print(f"{status} {len(text)} 字 ({elapsed:.1f}s)")
            
            all_text[list_idx] = text  # Replace
            if delay > 0:
                time.sleep(delay)
        
        print(f"   升級完成\n")
    elif auto_upgrade:
        print(f"\n✨ 所有頁面品質良好，無需升級\n")
    
    # Combine
    combined = "\n\n---\n\n".join(all_text)
    
    # Output
    if output_path:
        output_path = str(Path(output_path).expanduser().resolve())
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined)
        print(f"💾 已儲存: {output_path}")
        print(f"   總字數: {len(combined)}")
        if upgrade_pages:
            print(f"   已升級頁數: {len(upgrade_pages)}")
    
    return combined


QUALITY_PRESETS = {
    "fast":   {"model": "gemini-2.5-flash", "dpi": 200, "delay": 1.0},
    "normal": {"model": "gemini-2.5-flash", "dpi": 250, "delay": 1.5},
    "high":   {"model": "gemini-2.5-pro",   "dpi": 300, "delay": 3.0},
}


def main():
    parser = argparse.ArgumentParser(description="VLM OCR — 多模態視覺語言模型 PDF OCR")
    parser.add_argument("pdf", help="輸入 PDF 路徑")
    parser.add_argument("-o", "--output", help="輸出文字檔路徑 (預設: stdout)")
    parser.add_argument("-q", "--quality", choices=["fast", "normal", "high"], default="normal",
                        help="品質預設 (fast=Flash/200dpi, normal=Flash/250dpi, high=Pro/300dpi)")
    parser.add_argument("-m", "--model", default=None, help="手動指定模型 (覆蓋 --quality)")
    parser.add_argument("--dpi", type=int, default=None, help="手動指定 DPI (覆蓋 --quality)")
    parser.add_argument("--pages", help="頁碼範圍，如 1-10")
    parser.add_argument("--delay", type=float, default=None, help="頁間延遲秒數 (覆蓋 --quality)")
    parser.add_argument("--auto-upgrade", action="store_true", default=True,
                        help="自動偵測低品質頁面並用 Pro 重跑 (預設開啟)")
    parser.add_argument("--no-auto-upgrade", dest="auto_upgrade", action="store_false",
                        help="關閉自動升級")
    
    args = parser.parse_args()
    
    # Apply quality preset, then let explicit flags override
    preset = QUALITY_PRESETS[args.quality]
    model = args.model or preset["model"]
    dpi = args.dpi if args.dpi is not None else preset["dpi"]
    delay = args.delay if args.delay is not None else preset["delay"]
    
    print(f"📋 品質: {args.quality} → 模型={model}, DPI={dpi}, delay={delay}s, auto-upgrade={'ON' if args.auto_upgrade else 'OFF'}")
    
    result = run_vlm_ocr(
        pdf_path=args.pdf,
        output_path=args.output,
        model=model,
        dpi=dpi,
        page_range=args.pages,
        delay=delay,
        auto_upgrade=args.auto_upgrade,
    )
    
    if not args.output:
        print("\n" + "="*60)
        print(result)


if __name__ == "__main__":
    main()
