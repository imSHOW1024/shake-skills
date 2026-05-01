"""
icons.py — Brand icon registry for lecture-transcribe pipeline.

Two output modes:
  1. Markdown [Brand] text tags — for Obsidian / plain MD
  2. Notion custom_emoji mention blocks — for Notion API rich_text

SVG files stored in ./icons/ directory (claude.svg, gemini.svg, etc.)
Notion custom emoji registry loaded from notion_emoji_registry.json
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

ICON_DIR = Path(__file__).parent / 'icons'
EMOJI_REGISTRY_PATH = Path(__file__).parent / 'notion_emoji_registry.json'

# ── Notion custom emoji registry (lazy-loaded) ──
_notion_emoji_cache: Optional[dict] = None


def _load_notion_emoji_registry() -> dict:
    global _notion_emoji_cache
    if _notion_emoji_cache is not None:
        return _notion_emoji_cache
    try:
        _notion_emoji_cache = json.loads(EMOJI_REGISTRY_PATH.read_text(encoding='utf-8'))
    except Exception:
        _notion_emoji_cache = {}
    return _notion_emoji_cache


# ── Brand mapping ──
# Model ID substring → (brand_name, notion_custom_emoji_name)
_BRAND_MAP = [
    ('openai-codex', 'OpenAI', 'chatgpt'),
    ('anthropic', 'Claude', 'claude'),
    ('claude', 'Claude', 'claude'),
    ('gemini', 'Gemini', 'gemini-color'),
    ('google', 'Gemini', 'gemini-color'),
    ('openai', 'OpenAI', 'chatgpt'),
    ('codex', 'OpenAI', 'chatgpt'),
    ('gpt', 'OpenAI', 'chatgpt'),
    ('minimax', 'MiniMax', 'minimax-color'),
    ('notion', 'Notion', 'notion'),
    ('obsidian', 'Obsidian', None),
    ('openclaw', 'OpenClaw', 'openclaw-dark'),
    ('perplexity', 'Perplexity', None),
    ('antigravity', 'Antigravity', None),
]

# Service name → notion_custom_emoji_name (for footer lines)
_SERVICE_EMOJI_MAP = {
    'notion': 'notion',
    'obsidian': 'obsidian-color',   # ✅ Notion workspace has obsidian-color custom emoji
    'openclaw': 'openclaw-dark',
}


def brand_name(model_or_service: str) -> str:
    """Resolve a model ID or service name to a human-readable brand name."""
    s = (model_or_service or '').lower()
    for key, name, _ in _BRAND_MAP:
        if key in s:
            return name
    return ''


def _notion_emoji_name(model_or_service: str) -> Optional[str]:
    """Resolve a model ID to a Notion custom_emoji name."""
    s = (model_or_service or '').lower()
    for key, _, emoji_name in _BRAND_MAP:
        if key in s:
            return emoji_name
    return None


# ── Markdown text tags ──

def model_tag(model_id: str) -> str:
    """Return a [Brand] text tag for Obsidian/plain MD, or '' if unknown."""
    b = brand_name(model_id)
    return f'[{b}]' if b else ''


def service_tag(service: str) -> str:
    """Return a [Service] text tag for Obsidian/plain MD."""
    b = brand_name(service)
    return f'[{b}]' if b else ''


def markdown_emoji_tag(emoji_name: str) -> str:
    """Return a :emoji-name: token for markdown/Obsidian, or '' if unknown."""
    if not emoji_name:
        return ''
    return f':{emoji_name}:'


def model_emoji_tag(model_id: str) -> str:
    """Return a markdown emoji token for a model brand, or '' if unknown."""
    return markdown_emoji_tag(_notion_emoji_name(model_id) or '')


def service_emoji_tag(service: str) -> str:
    """Return a markdown emoji token for a service, or '' if unknown."""
    return markdown_emoji_tag(_SERVICE_EMOJI_MAP.get((service or '').lower(), ''))


# ── Notion custom_emoji mention ──

def notion_emoji_mention(emoji_name: str) -> Optional[dict]:
    """Return a Notion rich_text mention item for a custom_emoji, or None.

    Usage in rich_text arrays:
        rt = [notion_emoji_mention('claude'), text_block(' Final 指定模型：...')]
    """
    if not emoji_name:
        return None
    registry = _load_notion_emoji_registry()
    entry = registry.get(emoji_name)
    if not entry:
        return None
    return {
        "type": "mention",
        "mention": {
            "type": "custom_emoji",
            "custom_emoji": {
                "id": entry['id'],
                "name": entry['name'],
            }
        },
        "annotations": {
            "bold": False,
            "italic": True,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
        "plain_text": f":{entry['name']}:",
    }


def notion_model_emoji(model_id: str) -> Optional[dict]:
    """Return a Notion rich_text mention for a model's brand emoji, or None."""
    emoji_name = _notion_emoji_name(model_id)
    return notion_emoji_mention(emoji_name)


def notion_service_emoji(service: str) -> Optional[dict]:
    """Return a Notion rich_text mention for a service's emoji, or None."""
    emoji_name = _SERVICE_EMOJI_MAP.get(service.lower())
    return notion_emoji_mention(emoji_name)


# ── SVG file access ──

_SVG_FILE = {
    'Claude': 'claude',
    'Gemini': 'gemini',
    'OpenAI': 'openai',
    'MiniMax': 'minimax',
    'Notion': 'notion',
    'Obsidian': 'obsidian',
    'OpenClaw': 'openclaw',
    'Perplexity': 'perplexity',
    'Antigravity': 'antigravity',
}


def get_svg_path(brand: str) -> Optional[Path]:
    fname = _SVG_FILE.get(brand) or _SVG_FILE.get(brand_name(brand))
    if not fname:
        return None
    p = ICON_DIR / f'{fname}.svg'
    return p if p.exists() else None


def get_svg_content(brand: str) -> str:
    p = get_svg_path(brand)
    if not p:
        return ''
    try:
        return p.read_text(encoding='utf-8').strip()
    except Exception:
        return ''
