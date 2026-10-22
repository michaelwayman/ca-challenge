from datetime import UTC, datetime

import pytest

from ca_authlib.ids import user_id_from_wp_id
from catalog.management.commands.wp_migration.importer import Importer, PruneRefused
from catalog.models import Brand, Industry, Page, Review, Reviewer

from .fake_source import (
    FakeSource,
    brand_post,
    page_post,
    review_post,
    standard_source,
    term,
    user,
)

pytestmark = pytest.mark.django_db


def run(source, **kwargs):
    return Importer(source, **kwargs).run()


def test_first_run_creates_everything_with_relations():
    report = run(standard_source())

    assert report.counts["brands"].created == 1
    brand = Brand.objects.get()
    assert brand.slug == "acme"
    assert brand.founded_year == 1985
    assert brand.seo == {"title": "Acme reviews", "description": "Read about Acme"}
    assert [i.slug for i in brand.industries.all()] == ["insurance"]
    review = Review.objects.get()
    assert review.brand == brand
    assert review.rating == 5
    assert review.reviewer_location == "Albany, NY"
    assert review.published_at == datetime(2026, 5, 19, 20, 29, 13, tzinfo=UTC)


def test_reviewer_is_linked_by_deterministic_auth_id():
    run(standard_source())

    assert Reviewer.objects.get().auth_user_id == user_id_from_wp_id(2)


def test_rerun_changes_nothing():
    run(standard_source())

    report = run(standard_source())

    for counts in report.counts.values():
        assert (counts.created, counts.updated, counts.pruned) == (0, 0, 0)
    assert (Brand.objects.count(), Review.objects.count(), Reviewer.objects.count()) == (1, 1, 1)
    assert Industry.objects.count() == 1


def test_changes_in_wordpress_are_applied_including_slugs():
    run(standard_source())

    report = run(
        standard_source(
            brands=[brand_post(slug="acme-new", title="Acme Renamed")],
            reviews=[review_post(rating="3")],
        )
    )

    brand = Brand.objects.get()
    assert (brand.slug, brand.name) == ("acme-new", "Acme Renamed")
    assert Review.objects.get().rating == 3
    assert report.counts["brands"].updated == 1
    assert report.counts["reviews"].updated == 1


def test_industry_link_change_counts_as_a_brand_update():
    run(standard_source(industries=[term(), term(3, "Telecom", "telecom")]))

    report = run(
        standard_source(industries=[term(), term(3, "Telecom", "telecom")], links={7: [3]})
    )

    assert [i.slug for i in Brand.objects.get().industries.all()] == ["telecom"]
    assert report.counts["brands"].updated == 1


def test_an_unedited_description_follows_wordpress():
    run(standard_source())

    run(standard_source(brands=[brand_post(content="<p>Completely new body text</p>")]))

    brand = Brand.objects.get()
    assert brand.description == "<p>Completely new body text</p>"
    assert brand.wp_description == brand.description


def test_an_edited_description_survives_reruns_even_when_wordpress_changes():
    run(standard_source())
    brand = Brand.objects.get()
    brand.description = "<p>Edited by an editor</p>"
    brand.save()

    report = run(standard_source(brands=[brand_post(content="<p>Completely new body text</p>")]))

    brand.refresh_from_db()
    assert brand.description == "<p>Edited by an editor</p>"
    assert brand.wp_description == "<p>Completely new body text</p>"  # what WordPress said
    assert report.counts["brands"].updated == 1


def test_a_second_identical_run_changes_nothing():
    run(standard_source())

    report = run(standard_source())

    assert report.counts["brands"].unchanged == 1


def test_html_is_sanitized():
    dirty = '<p>Hi<script>alert(1)</script><a href="javascript:x" onclick="y()">z</a></p>'

    run(standard_source(reviews=[review_post(content=dirty)]))

    body = Review.objects.get().body
    assert "<script" not in body
    assert "javascript:" not in body
    assert "onclick" not in body
    assert "<p>Hi" in body


def test_review_with_invalid_rating_is_skipped_with_a_warning():
    report = run(standard_source(reviews=[review_post(rating="9")]))

    assert Review.objects.count() == 0
    assert report.counts["reviews"].skipped == 1
    assert any("invalid rating" in w for w in report.warnings)


def test_review_for_unknown_brand_is_skipped_with_a_warning():
    report = run(standard_source(reviews=[review_post(brand="999")]))

    assert Review.objects.count() == 0
    assert any("unknown brand" in w for w in report.warnings)


def test_only_review_authors_become_reviewers():
    run(standard_source(users=[user(), user(1, "admin")]))

    assert [r.wp_id for r in Reviewer.objects.all()] == [2]


def test_reviewer_name_mismatch_is_reported_not_silently_dropped():
    report = run(standard_source(reviews=[review_post(reviewer_name="Someone Else")]))

    assert Reviewer.objects.get().display_name == "Sarah K."
    assert any("differs from the author's display name" in w for w in report.warnings)


def test_dry_run_reports_creates_but_saves_nothing():
    report = run(standard_source(), dry_run=True)

    assert report.counts["brands"].created == 1
    assert Brand.objects.count() == 0
    assert Review.objects.count() == 0


class TestPrune:
    def test_default_never_deletes(self):
        run(standard_source())

        run(FakeSource(industries=[term()], brands=[brand_post(wp_id=8, slug="other")]))

        assert Brand.objects.filter(wp_id=7).exists()

    def test_prune_removes_rows_missing_from_wordpress_and_their_reviews(self):
        run(standard_source())

        report = run(
            standard_source(
                brands=[brand_post(wp_id=8, slug="other")],
                reviews=[review_post(wp_id=13, slug="other-review", brand="8")],
                links={},
            ),
            prune=True,
        )

        assert list(Brand.objects.values_list("wp_id", flat=True)) == [8]
        assert list(Review.objects.values_list("wp_id", flat=True)) == [13]
        assert report.counts["brands"].pruned == 1
        assert report.counts["reviews"].pruned == 1

    def test_prune_keeps_rows_created_natively(self):
        run(standard_source())
        native = Brand.objects.create(slug="native", name="Native")

        run(standard_source(), prune=True)

        assert Brand.objects.filter(pk=native.pk).exists()

    def test_prune_refuses_when_the_source_returns_nothing(self):
        run(standard_source())

        with pytest.raises(PruneRefused):
            run(FakeSource(), prune=True)

        assert Brand.objects.count() == 1

    def test_prune_with_dry_run_reports_but_deletes_nothing(self):
        run(standard_source())

        report = run(
            standard_source(
                brands=[brand_post(wp_id=8, slug="other")],
                reviews=[review_post(wp_id=13, slug="other-review", brand="8")],
                links={},
            ),
            prune=True,
            dry_run=True,
        )

        assert report.counts["brands"].pruned == 1
        assert Brand.objects.filter(wp_id=7).exists()


class TestPages:
    def test_imports_pages_with_sanitized_bodies(self):
        report = run(
            standard_source(pages=[page_post(content="<p>Hi</p><script>alert(1)</script>")])
        )

        page = Page.objects.get()
        assert (page.slug, page.title, page.wp_id) == ("about", "About", 5)
        assert "<script" not in page.body
        assert "<p>Hi</p>" in page.body
        assert report.counts["pages"].created == 1

    def test_the_front_page_is_left_out(self):
        home = page_post(wp_id=4, slug="home", title="Home")

        run(standard_source(pages=[home, page_post()], front_page=4))

        assert [p.slug for p in Page.objects.all()] == ["about"]

    def test_a_wordpress_without_a_static_front_page_keeps_every_page(self):
        run(standard_source(pages=[page_post(wp_id=4, slug="home", title="Home"), page_post()]))

        assert Page.objects.count() == 2

    def test_nested_pages_are_skipped_with_a_warning(self):
        report = run(standard_source(pages=[page_post(wp_id=9, slug="team", parent_id=5)]))

        assert Page.objects.count() == 0
        assert report.counts["pages"].skipped == 1
        assert any("nested" in w for w in report.warnings)

    @pytest.mark.parametrize("slug", ["brand", "review", "api", "static", "admin", "healthz"])
    def test_a_slug_that_would_shadow_a_route_is_skipped_with_a_warning(self, slug):
        report = run(standard_source(pages=[page_post(slug=slug)]))

        assert Page.objects.count() == 0
        assert any("collides" in w for w in report.warnings)

    def test_rerun_changes_nothing_and_edits_are_picked_up(self):
        run(standard_source(pages=[page_post()]))

        again = run(standard_source(pages=[page_post()]))
        edited = run(standard_source(pages=[page_post(title="About us")]))

        assert (again.counts["pages"].created, again.counts["pages"].unchanged) == (0, 1)
        assert edited.counts["pages"].updated == 1
        assert Page.objects.get().title == "About us"

    def test_prune_removes_pages_gone_from_wordpress_but_keeps_native_ones(self):
        run(
            standard_source(
                pages=[page_post(), page_post(wp_id=6, slug="contact", title="Contact")]
            )
        )
        native = Page.objects.create(slug="made-here", title="Made here")

        report = run(standard_source(pages=[page_post()]), prune=True)

        assert sorted(Page.objects.values_list("slug", flat=True)) == ["about", "made-here"]
        assert report.counts["pages"].pruned == 1
        assert Page.objects.filter(pk=native.pk).exists()
