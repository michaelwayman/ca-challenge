import re

from django.db.models import Exists, F, OuterRef
from rest_framework.exceptions import ValidationError

from catalog.models import Brand

ORDERING_FIELDS = ("name", "average_rating", "review_count")
SLUG = re.compile(r"[-a-zA-Z0-9_]+")


def filter_by_industry(queryset, slugs: list[str]):
    """Brands in any of the given industries (OR). Uses EXISTS rather than a join so a
    brand in several industries is neither duplicated nor double counted in the stats."""
    asked = [s for s in slugs if s]
    if not asked:
        return queryset
    # A value that cannot be a slug (a NUL byte, say, which Postgres rejects) cannot match
    # anything either: it is an unknown industry, not a server error.
    slugs = [s for s in asked if SLUG.fullmatch(s)]
    if not slugs:
        return queryset.none()
    in_industry = Brand.industries.through.objects.filter(
        brand_id=OuterRef("pk"), industry__slug__in=slugs
    )
    return queryset.filter(Exists(in_industry))


def order_brands(queryset, raw: str | None):
    """Apply ?ordering=. Unreviewed brands sort last on rating in both directions, and
    name then id break ties so pagination is stable."""
    names = [part.strip() for part in (raw or "name").split(",") if part.strip()]
    unknown = [n for n in names if n.lstrip("-") not in ORDERING_FIELDS]
    if unknown:
        allowed = ", ".join(ORDERING_FIELDS)
        raise ValidationError(
            {"ordering": f"Unknown field(s) {unknown}. Allowed: {allowed} (prefix - to reverse)."}
        )
    expressions = []
    for name in names:
        field = F(name.lstrip("-"))
        expressions.append(
            field.desc(nulls_last=True) if name.startswith("-") else field.asc(nulls_last=True)
        )
    return queryset.order_by(*expressions, "name", "pk")
