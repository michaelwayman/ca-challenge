from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

from django import template

from catalog import text

register = template.Library()


@register.inclusion_tag("catalog/_stars.html")
def stars(rating, show_value=False):
    """Five stars filled to the nearest whole star; the exact value goes in the label."""
    if rating is None:
        return {"rating": None}
    filled = int(Decimal(str(rating)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    filled = max(0, min(5, filled))
    return {
        "rating": rating,
        "full": range(filled),
        "empty": range(5 - filled),
        "show_value": show_value,
    }


@register.filter
def excerpt(html, words=24):
    """The first `words` words of an HTML body as plain text. The result is not marked safe,
    so autoescaping encodes it exactly once (striptags + truncatewords would escape the
    entities in sanitized HTML a second time and show "AT&amp;T" to the reader)."""
    return text.excerpt(html, int(words))


@register.filter
def web_host(url):
    """Hostname of an http(s) URL, or '' for anything else (never link a javascript: URL)."""
    parsed = urlparse(url or "")
    return parsed.hostname or "" if parsed.scheme in ("http", "https") else ""
