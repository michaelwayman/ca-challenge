from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC

from django.db import models, transaction

from ca_authlib.ids import user_id_from_wp_id
from catalog.models import RESERVED_PAGE_SLUGS, Brand, Industry, Page, Review, Reviewer
from catalog.sanitize import sanitize_html

from .source import WordPressSource, WPPost


class PruneRefused(Exception):
    """Pruning was requested but the source returned nothing for a model that has data."""


@dataclass
class Counts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    pruned: int = 0


@dataclass
class ImportReport:
    counts: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    warnings: list[str] = field(default_factory=list)


class Importer:
    """Idempotent WordPress -> catalog import, keyed on wp_id.

    Everything runs in one transaction. A dry run does the full work and rolls back,
    so its counts are exactly what a real run would produce.
    """

    def __init__(self, source: WordPressSource, *, prune: bool = False, dry_run: bool = False):
        self.source = source
        self.prune = prune
        self.dry_run = dry_run
        self.report = ImportReport()

    def run(self) -> ImportReport:
        with transaction.atomic():
            terms = self.source.industries()
            brands = self.source.brands()
            reviews = self.source.reviews()
            pages = self.source.pages()
            front_page_id = self.source.front_page_id()
            author_ids = {r.author_id for r in reviews}
            users = [u for u in self.source.users() if u.wp_id in author_ids]

            industries = self._import_industries(terms)
            brand_map = self._import_brands(brands, industries)
            reviewer_map = self._import_reviewers(users)
            self._import_reviews(reviews, brand_map, reviewer_map)
            importable_pages = self._import_pages(pages, front_page_id)
            if self.prune:
                self._prune(
                    [
                        (Review, {r.wp_id for r in reviews}),
                        (Reviewer, {u.wp_id for u in users}),
                        (Brand, {b.wp_id for b in brands}),
                        (Industry, {t.wp_id for t in terms}),
                        (Page, {p.wp_id for p in importable_pages}),
                    ]
                )
            if self.dry_run:
                transaction.set_rollback(True)
        return self.report

    def _import_industries(self, terms) -> dict[int, Industry]:
        existing = self._existing(Industry)
        for term in terms:
            obj, status = self._sync(
                Industry, existing, term.wp_id, {"name": term.name, "slug": term.slug}
            )
            self._count(Industry, status)
        return existing

    def _import_brands(self, brands: list[WPPost], industries: dict[int, Industry]):
        existing = self._existing(Brand)
        links = self.source.brand_industries()
        for post in brands:
            meta = post.meta
            description = sanitize_html(post.content)
            current = existing.get(post.wp_id)
            # Text edited here (the API or the admin) differs from what was last imported, and
            # is kept; text nobody has touched follows WordPress.
            edited = current is not None and current.description != current.wp_description
            values = {
                "slug": post.slug,
                "name": post.title,
                "wp_description": description,
                "website_url": meta.get("website_url", ""),
                "founded_year": _to_int(meta.get("founded_year")),
                "headquarters": meta.get("headquarters", ""),
                "seo": {
                    "title": meta.get("_yoast_wpseo_title", ""),
                    "description": meta.get("_yoast_wpseo_metadesc", ""),
                },
            }
            if not edited:
                values["description"] = description
            brand, status = self._sync(Brand, existing, post.wp_id, values)
            wanted = {industries[t].pk for t in links.get(post.wp_id, []) if t in industries}
            if wanted != set(brand.industries.values_list("pk", flat=True)):
                brand.industries.set(wanted)
                if status == "unchanged":
                    status = "updated"
            self._count(Brand, status)
        return existing

    def _import_reviewers(self, users) -> dict[int, Reviewer]:
        existing = self._existing(Reviewer)
        for user in users:
            values = {
                "display_name": user.display_name,
                "auth_user_id": user_id_from_wp_id(user.wp_id),
            }
            _, status = self._sync(Reviewer, existing, user.wp_id, values)
            self._count(Reviewer, status)
        return existing

    def _import_reviews(self, reviews, brands: dict[int, Brand], reviewers: dict[int, Reviewer]):
        existing = self._existing(Review)
        name_mismatches = 0
        for post in reviews:
            rating = _to_int(post.meta.get("rating"))
            brand = brands.get(_to_int(post.meta.get("brand")) or 0)
            if rating is None or not 1 <= rating <= 5:
                self._skip(Review, f"review {post.wp_id} ({post.slug}): invalid rating")
                continue
            if brand is None:
                self._skip(Review, f"review {post.wp_id} ({post.slug}): unknown brand")
                continue
            reviewer = reviewers.get(post.author_id)
            if reviewer is None:
                self.report.warnings.append(f"review {post.wp_id}: author has no reviewer row")
            elif post.meta.get("reviewer_name", reviewer.display_name) != reviewer.display_name:
                name_mismatches += 1
            values = {
                "slug": post.slug,
                "title": post.title,
                "body": sanitize_html(post.content),
                "rating": rating,
                "brand": brand,
                "reviewer": reviewer,
                "reviewer_location": post.meta.get("reviewer_location", ""),
                "published_at": post.published_gmt.replace(tzinfo=UTC),
            }
            _, status = self._sync(Review, existing, post.wp_id, values)
            self._count(Review, status)
        if name_mismatches:
            self.report.warnings.append(
                f"{name_mismatches} reviews have a reviewer_name that differs from the "
                "author's display name; the display name was kept"
            )

    def _import_pages(self, pages: list[WPPost], front_page_id: int | None) -> list[WPPost]:
        """Static pages. The page WordPress uses as its home page is left out (the front page
        is the dynamic one here); nested pages and slugs that would shadow a route are
        skipped with a warning."""
        existing = self._existing(Page)
        importable = []
        for post in pages:
            if post.wp_id == front_page_id:
                continue
            if post.parent_id:
                self._skip(Page, f"page {post.wp_id} ({post.slug}): nested pages are not supported")
                continue
            if post.slug in RESERVED_PAGE_SLUGS:
                self._skip(Page, f"page {post.wp_id} ({post.slug}): slug collides with a route")
                continue
            values = {"slug": post.slug, "title": post.title, "body": sanitize_html(post.content)}
            _, status = self._sync(Page, existing, post.wp_id, values)
            self._count(Page, status)
            importable.append(post)
        return importable

    def _prune(self, targets: list[tuple[type[models.Model], set[int]]]):
        for model, source_ids in targets:
            local = model.objects.filter(wp_id__isnull=False)
            if not source_ids and local.exists():
                raise PruneRefused(
                    f"source returned no {model._meta.verbose_name_plural}; refusing to prune"
                )
            stale = local.exclude(wp_id__in=source_ids)
            self.report.counts[model._meta.verbose_name_plural].pruned += stale.count()
            stale.delete()

    @staticmethod
    def _existing(model) -> dict[int, models.Model]:
        return {o.wp_id: o for o in model.objects.filter(wp_id__isnull=False)}

    @staticmethod
    def _sync(model, existing, wp_id, values):
        obj = existing.get(wp_id)
        if obj is None:
            obj = model.objects.create(wp_id=wp_id, **values)
            existing[wp_id] = obj
            return obj, "created"
        changed = [name for name, value in values.items() if getattr(obj, name) != value]
        if not changed:
            return obj, "unchanged"
        for name in changed:
            setattr(obj, name, values[name])
        obj.save(update_fields=[*changed, "updated_at"])
        return obj, "updated"

    def _count(self, model, status: str):
        counts = self.report.counts[model._meta.verbose_name_plural]
        setattr(counts, status, getattr(counts, status) + 1)

    def _skip(self, model, message: str):
        self.report.counts[model._meta.verbose_name_plural].skipped += 1
        self.report.warnings.append(message)


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None
