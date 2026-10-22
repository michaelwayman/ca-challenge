import nh3

ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "em", "h2", "h3", "h4", "i", "li", "ol", "p", "strong", "ul",
}  # fmt: skip


def sanitize_html(html: str) -> str:
    """Strip everything outside a small allowlist.

    Stored HTML is rendered with |safe, so the models call this in save(); the importer and the
    API call it too, to check what they are given before it reaches a model.
    """
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes={"a": {"href"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )
