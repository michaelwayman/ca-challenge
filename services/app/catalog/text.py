import re
from html import unescape

from django.utils.text import Truncator

SNIPPET_LENGTH = 140
EXCERPT_WORDS = 25


def plain_text(html: str) -> str:
    """HTML to plain text: tags become spaces, entities are decoded, whitespace collapsed."""
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", html)).split())


def excerpt(html: str, words: int = EXCERPT_WORDS) -> str:
    """The first `words` words of an HTML body as plain text (what the brand cards show).

    Tags are dropped and entities decoded, so the result is text, not markup: render it
    escaped (autoescaping, or a React text node), never as HTML.
    """
    return Truncator(plain_text(html or "")).words(words)


def snippet(html: str, limit: int = SNIPPET_LENGTH) -> str:
    """Plain-text preview of an HTML body, cut at a word boundary with an ellipsis.

    The result is plain text (entities decoded), so clients must render it as text,
    never as HTML.
    """
    text = plain_text(html)
    if len(text) <= limit:
        return text
    head = text[:limit]
    if text[limit] != " ":  # the cut falls mid-word: back up to the previous space
        space = head.rfind(" ")
        if space > 0:
            head = head[:space]
    return head.rstrip(" ,;:.-") + "…"
