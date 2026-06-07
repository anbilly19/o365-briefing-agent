"""Email body cleaning pipeline.

Steps:
  1. Detect HTML vs plain text.
  2. Strip HTML using html2text (primary) or BeautifulSoup (fallback).
  3. Collapse whitespace / quoted reply chains.
  4. Append attachment filenames as a metadata note.
  5. Normalise to plain UTF-8.

No content is downloaded — attachments are represented only as their
filenames, sourced from Graph API metadata.
"""

from __future__ import annotations

import re

try:
    import html2text as _html2text
    _H2T_AVAILABLE = True
except ImportError:
    _H2T_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


_QUOTED_REPLY_RE = re.compile(
    r"(-{3,}\s*(Original Message|On .+ wrote).*)",
    re.IGNORECASE | re.DOTALL,
)
_WHITESPACE_RE = re.compile(r"\n{3,}")


def _strip_html_h2t(html: str) -> str:
    h = _html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # don't wrap
    return h.handle(html)


def _strip_html_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)


def _strip_html_naive(html: str) -> str:
    """Last-resort: regex tag stripping with no dependencies."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"&[a-z]+;", " ", text)


def strip_html(html: str) -> str:
    """Strip HTML to plain text, trying html2text → BS4 → regex fallback."""
    if _H2T_AVAILABLE:
        return _strip_html_h2t(html)
    if _BS4_AVAILABLE:
        return _strip_html_bs4(html)
    return _strip_html_naive(html)


def is_html(text: str) -> bool:
    """Heuristic: does this look like HTML?"""
    stripped = text.lstrip()[:200].lower()
    return stripped.startswith("<html") or "<body" in stripped or "<div" in stripped


def clean_body(
    raw_body: str,
    attachments: list[str] | None = None,
    max_chars: int | None = None,
) -> str:
    """Clean an email body and append attachment metadata.

    Args:
        raw_body:    The raw body string (HTML or plain text).
        attachments: List of attachment filenames from Graph API metadata.
        max_chars:   If given, truncate the cleaned body to this many chars.

    Returns:
        A clean UTF-8 plain-text string suitable for LLM input.
    """
    text = raw_body

    # 1. Strip HTML if needed
    if is_html(text):
        text = strip_html(text)

    # 2. Remove quoted reply chains (keep only the latest message)
    text = _QUOTED_REPLY_RE.sub("", text)

    # 3. Collapse excessive blank lines
    text = _WHITESPACE_RE.sub("\n\n", text).strip()

    # 4. Truncate if a budget cap is given
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]

    # 5. Append attachment note at the end (after truncation, always included)
    if attachments:
        note = "[Attachments: " + ", ".join(attachments) + "]"
        text = f"{text}\n{note}"

    return text
