"""Text utilities for JD hydration."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Tags whose closing boundary warrants a paragraph break in plain text.
_BLOCK_TAGS = frozenset({"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"})


def strip_html_to_text(html: str) -> str:
    """Convert an HTML string to clean plain text with paragraph breaks.

    - Block-level elements (p, div, li, headings, tr) produce \\n\\n boundaries.
    - <br> tags produce a single \\n.
    - All remaining tags are stripped.
    - Consecutive blank lines are collapsed to a single blank line.
    - Returns the original string unchanged when it contains no HTML tags
      (safe to call on already-plain text).
    """
    if not html:
        return html

    # Fast path: no angle brackets means no HTML — avoid BeautifulSoup overhead.
    if "<" not in html:
        return html.strip()

    soup = BeautifulSoup(html, "html.parser")

    # Replace <br> with a newline placeholder before extracting text.
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Insert sentinel strings after block elements so that get_text() produces
    # paragraph breaks at the right boundaries.
    _SENTINEL = "\x00BLOCK\x00"
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after(_SENTINEL)

    raw = soup.get_text(separator="")
    text = raw.replace(_SENTINEL, "\n\n")

    # Collapse runs of 3+ newlines down to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace on each line.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
