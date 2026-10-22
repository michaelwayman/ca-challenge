from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import Brand, Industry, Review

pytestmark = pytest.mark.django_db


def make_review(brand, rating, slug, **kwargs):
    return Review.objects.create(
        slug=slug, title=slug, rating=rating, brand=brand, published_at=timezone.now(), **kwargs
    )


def test_with_stats_derives_rounded_average_and_count():
    brand = Brand.objects.create(slug="a", name="A")
    for i, rating in enumerate([5, 4, 4]):
        make_review(brand, rating, f"r{i}")

    stats = Brand.objects.with_stats().get(pk=brand.pk)

    assert stats.average_rating == Decimal("4.3")
    assert stats.review_count == 3


def test_with_stats_for_unreviewed_brand_is_null_and_zero():
    Brand.objects.create(slug="a", name="A")

    stats = Brand.objects.with_stats().get()

    assert stats.average_rating is None
    assert stats.review_count == 0


@pytest.mark.parametrize("rating", [0, 6])
def test_rating_outside_1_to_5_is_rejected(rating):
    brand = Brand.objects.create(slug="a", name="A")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_review(brand, rating, "bad")


def test_many_rows_can_lack_a_wp_id():
    Industry.objects.create(name="One", slug="one")
    Industry.objects.create(name="Two", slug="two")

    assert Industry.objects.filter(wp_id__isnull=True).count() == 2


def test_reviews_are_newest_first_with_id_as_tiebreaker():
    brand = Brand.objects.create(slug="a", name="A")
    when = timezone.now()
    first = Review.objects.create(slug="x", title="x", rating=5, brand=brand, published_at=when)
    second = Review.objects.create(slug="y", title="y", rating=5, brand=brand, published_at=when)

    assert list(brand.reviews.all()) == [second, first]


UNSAFE = '<p onclick="x()">Hi</p><script>alert(1)</script><a href="javascript:x()">link</a>'


class TestStoredHtmlIsSanitizedOnSave:
    """The templates render these fields with |safe, so no write path may store unsafe markup."""

    @staticmethod
    def assert_safe(text):
        assert "<script" not in text
        assert "onclick" not in text
        assert "javascript:" not in text
        assert text.startswith("<p>Hi</p>")

    def test_brand_description(self):
        brand = Brand.objects.create(slug="a", name="A", description=UNSAFE)

        self.assert_safe(Brand.objects.get(pk=brand.pk).description)

    def test_brand_description_when_edited_later(self):
        brand = Brand.objects.create(slug="a", name="A", description="<p>ok</p>")
        brand.description = UNSAFE
        brand.save(update_fields=["description"])

        self.assert_safe(Brand.objects.get(pk=brand.pk).description)

    def test_review_body(self):
        brand = Brand.objects.create(slug="a", name="A")
        review = make_review(brand, 5, "r", body=UNSAFE)

        self.assert_safe(Review.objects.get(pk=review.pk).body)

    def test_clean_html_is_left_alone(self):
        link = '<a href="https://x.example" rel="noopener noreferrer nofollow">three</a>'
        html = f"<p>One <strong>two</strong> {link}</p>"
        brand = Brand.objects.create(slug="a", name="A", description=html)

        assert Brand.objects.get(pk=brand.pk).description == html
