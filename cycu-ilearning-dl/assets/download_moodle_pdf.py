#!/usr/bin/env python3
"""
Moodle pdfannotator PDF 下載工具
用法: python3 download_moodle_pdf.py <url> <moodle_session> <output_filename>
"""

import sys
import re
import requests
from pathlib import Path
from urllib.parse import urljoin

COOKIE_VALUE = "9t68oar56p0sahlj2kpancmqp1"

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


def check_cookie_valid(html: str, final_url: str) -> None:
    """若偵測到登入頁面或 session 過期，立即終止並提示"""
    if "login" in final_url.lower() or re.search(
        r'(?:You are not logged in|請先登入|loginform|id=["\']login)', html, re.IGNORECASE
    ):
        print("[錯誤] Cookie 已失效，請重新登入 iLearning 並取得新的 MoodleSession 值。")
        sys.exit(2)


def get_page_title(html: str) -> str | None:
    """從頁面 HTML 擷取標題（h2 非區塊/傳訊的那個）"""
    for m in re.findall(r'<h[12][^>]*>(.*?)</h[12]>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m).strip()
        if text and text not in ('區塊', '傳訊'):
            return text
    return None


def get_pdf_url(page_url: str, session_cookie: str) -> tuple[str | None, str | None]:
    """從 pdfannotator 頁面解析出實際 PDF URL 及頁面標題"""
    headers = {
        **HEADERS_BASE,
        "Cookie": f"MoodleSession={session_cookie}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print(f"[1/3] 取得頁面: {page_url}")
    resp = requests.get(page_url, headers=headers, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    check_cookie_valid(html, resp.url)

    title = get_page_title(html)

    # 策略 1: JSON-escaped URL (Moodle pdfannotator 將 URL 藏在 JS，斜線用 \/ 跳脫)
    m = re.search(r'(https?:\\/\\/[^\s"\'<>]*?\.pdf)', html, re.IGNORECASE)
    if m:
        return m.group(1).replace("\\/", "/"), title

    # 策略 2: <source src="...pdf...">
    m = re.search(r'<source[^>]+src=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        return urljoin(page_url, m.group(1)), title

    # 策略 3: JavaScript "file":"...pdf..."
    m = re.search(r'["\']file["\']\s*:\s*["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        return urljoin(page_url, m.group(1)), title

    # 策略 4: pluginfile.php 明文連結含 .pdf
    m = re.search(r'(https?://[^\s"\'<>]*pluginfile\.php[^\s"\'<>]*\.pdf[^\s"\'<>]*)', html, re.IGNORECASE)
    if m:
        return m.group(1), title

    # 策略 5: src 屬性含 pluginfile
    m = re.search(r'src=["\']([^"\']*pluginfile[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        return urljoin(page_url, m.group(1)), title

    print("[DEBUG] 找不到 PDF URL，輸出前 3000 字元供檢查:")
    print(html[:3000])
    return None, title


def download_pdf(pdf_url: str, session_cookie: str, output_path: Path) -> None:
    """下載 PDF 並儲存"""
    headers = {
        **HEADERS_BASE,
        "Cookie": f"MoodleSession={session_cookie}",
        "Referer": pdf_url,
    }

    print(f"[2/3] 下載 PDF: {pdf_url}")
    with requests.get(pdf_url, headers=headers, timeout=60, stream=True) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")

        # 若拿到 HTML（通常是被導向登入頁），視為 cookie 失效
        if "text/html" in content_type:
            print("[錯誤] Cookie 已失效，請重新登入 iLearning 並取得新的 MoodleSession 值。")
            sys.exit(2)

        if "pdf" not in content_type and "octet-stream" not in content_type:
            print(f"[警告] Content-Type 為 {content_type!r}，可能不是 PDF")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    size_kb = output_path.stat().st_size / 1024
    print(f"[3/3] 已儲存: {output_path}  ({size_kb:.1f} KB)")


def main():
    if len(sys.argv) == 4:
        url, cookie_value, filename = sys.argv[1], sys.argv[2], sys.argv[3]
    elif len(sys.argv) == 3:
        url, cookie_value = sys.argv[1], sys.argv[2]
        filename = None
    else:
        print("用法: python3 download_moodle_pdf.py <url> <moodle_session> [output_filename]")
        sys.exit(1)

    pdf_url, page_title = get_pdf_url(url, cookie_value)
    if not pdf_url:
        print("[錯誤] 無法從頁面解析出 PDF URL")
        sys.exit(1)

    # 未指定檔名時，從頁面標題自動產生
    if not filename:
        if page_title:
            filename = f"1142全球台商個案研討-{page_title}"
            print(f"[自動命名] {filename}")
        else:
            filename = "moodle_download"

    if not filename.endswith(".pdf"):
        filename += ".pdf"

    output = Path.home() / "Downloads" / filename

    print(f"[OK] 找到 PDF URL: {pdf_url}")
    download_pdf(pdf_url, cookie_value, output)
    print("[完成] 下載成功！")


if __name__ == "__main__":
    main()
