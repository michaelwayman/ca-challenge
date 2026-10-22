from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import Brand, Industry, Review, Reviewer

pytestmark = pytest.mark.django_db

URL = "/api/brands/"
NOW = timezone.now()


def make_brand(slug, industries=(), **kwargs):
    kwargs.setdefault("name", slug.title())
    brand = Brand.objects.create(slug=slug, **kwargs)
    for industry in industries:
        brand.industries.add(industry)
    return brand


def make_review(brand, slug, rating=5, age_days=0, **kwargs):
    kwargs.setdefault("title", slug.replace("-", " ").title())
    return Review.objects.create(
        slug=slug, rating=rating, brand=brand, published_at=NOW - timedelta(days=age_days), **kwargs
    )


@pytest.fixture
def industries():
    return {
        slug: Industry.objects.create(name=slug.title(), slug=slug)
        for slug in ("insurance", "telecom", "retail")
    }


def get(client, **params):
    response = client.get(URL, params)
    assert response.status_code == 200, response.content
    return response.json()


def slugs(data):
    return [row["slug"] for row in data["results"]]


class TestShape:
    def test_row_has_everything_a_card_needs(self, client, industries):
        brand = make_brand(
            "acme",
            [industries["insurance"]],
            name="Acme",
            description="<p>Short <em>text</em></p>",
        )
        reviewer = Reviewer.objects.create(display_name="Sarah K.")
        make_review(brand, "great", rating=5, body="<p>Loved it</p>", reviewer=reviewer)
        make_review(brand, "ok", rating=4)

        data = get(client)

        assert data["count"] == 1
        assert data["next"] is None
        assert data["previous"] is None
        assert data["results"] == [
            {
                "name": "Acme",
                "slug": "acme",
                "url": "/brand/acme/",
                "industries": [{"name": "Insurance", "slug": "insurance"}],
                "average_rating": 4.5,
                "review_count": 2,
                "excerpt": "Short text",
                "top_review": {
                    "slug": "great",
                    "title": "Great",
                    "rating": 5,
                    "snippet": "Loved it",
                    "reviewer": "Sarah K.",
                    "url": "/review/great/",
                },
            }
        ]

    def test_unreviewed_brand_has_null_rating_and_no_top_review(self, client):
        make_brand("acme")

        row = get(client)["results"][0]

        assert row["average_rating"] is None
        assert row["review_count"] == 0
        assert row["top_review"] is None

    def test_review_without_a_reviewer_has_null_reviewer(self, client):
        make_review(make_brand("acme"), "anon")

        assert get(client)["results"][0]["top_review"]["reviewer"] is None

    def test_is_public(self, client):
        assert client.get(URL).status_code == 200


class TestTopReview:
    def test_highest_rating_wins(self, client):
        brand = make_brand("acme")
        make_review(brand, "four-new", rating=4, age_days=0)
        make_review(brand, "five-old", rating=5, age_days=30)

        assert get(client)["results"][0]["top_review"]["slug"] == "five-old"

    def test_ties_go_to_the_most_recent(self, client):
        brand = make_brand("acme")
        make_review(brand, "old", rating=5, age_days=10)
        make_review(brand, "new", rating=5, age_days=1)

        assert get(client)["results"][0]["top_review"]["slug"] == "new"

    def test_remaining_ties_go_to_the_highest_id(self, client):
        brand = make_brand("acme")
        make_review(brand, "first", rating=5)
        make_review(brand, "second", rating=5)

        assert get(client)["results"][0]["top_review"]["slug"] == "second"

    def test_each_brand_gets_its_own_top_review(self, client):
        a, b = make_brand("a"), make_brand("b")
        make_review(a, "a-low", rating=2)
        make_review(a, "a-high", rating=5)
        make_review(b, "b-only", rating=3)

        tops = {row["slug"]: row["top_review"]["slug"] for row in get(client)["results"]}

        assert tops == {"a": "a-high", "b": "b-only"}

    def test_snippet_is_plain_text_cut_at_a_word(self, client):
        make_review(make_brand("acme"), "long", body="<p><b>Hello</b> " + "word " * 60 + "</p>")

        snippet = get(client)["results"][0]["top_review"]["snippet"]

        assert snippet.startswith("Hello word")
        assert "<" not in snippet
        assert snippet.endswith("word…")
        assert len(snippet) <= 141


class TestIndustryFilter:
    @pytest.fixture(autouse=True)
    def brands(self, industries):
        make_brand("acme", [industries["insurance"]])
        make_brand("swift", [industries["telecom"]])
        make_brand("urban", [industries["retail"]])

    def test_filters_to_one_industry(self, client):
        assert slugs(get(client, industry="telecom")) == ["swift"]

    def test_repeated_param_is_an_or(self, client):
        data = get(client, industry=["insurance", "retail"])

        assert slugs(data) == ["acme", "urban"]
        assert data["count"] == 2

    def test_unknown_slug_is_an_empty_page_not_an_error(self, client):
        data = get(client, industry="nope")

        assert data["results"] == []
        assert data["count"] == 0

    def test_empty_param_is_ignored(self, client):
        assert len(get(client, industry="")["results"]) == 3

    def test_brand_in_two_matching_industries_appears_once_with_correct_stats(
        self, client, industries
    ):
        both = make_brand("both", [industries["insurance"], industries["telecom"]])
        make_review(both, "r1", rating=5)
        make_review(both, "r2", rating=3)

        data = get(client, industry=["insurance", "telecom"])

        rows = [r for r in data["results"] if r["slug"] == "both"]
        assert len(rows) == 1
        assert (rows[0]["review_count"], rows[0]["average_rating"]) == (2, 4.0)
        assert data["count"] == 3  # acme, swift, both


class TestOrdering:
    @pytest.fixture(autouse=True)
    def brands(self):
        for slug, ratings in {"low": [2, 3], "high": [5, 5, 4], "none": [], "mid": [4]}.items():
            brand = make_brand(slug)
            for i, rating in enumerate(ratings):
                make_review(brand, f"{slug}-{i}", rating=rating)

    def test_default_is_by_name(self, client):
        assert slugs(get(client)) == ["high", "low", "mid", "none"]

    def test_average_rating_descending_puts_unreviewed_last(self, client):
        assert slugs(get(client, ordering="-average_rating")) == ["high", "mid", "low", "none"]

    def test_average_rating_ascending_still_puts_unreviewed_last(self, client):
        assert slugs(get(client, ordering="average_rating")) == ["low", "mid", "high", "none"]

    def test_review_count(self, client):
        assert slugs(get(client, ordering="-review_count")) == ["high", "low", "mid", "none"]
        assert slugs(get(client, ordering="review_count"))[0] == "none"

    def test_name_descending(self, client):
        assert slugs(get(client, ordering="-name")) == ["none", "mid", "low", "high"]

    def test_unknown_field_is_a_400_with_a_message(self, client):
        response = client.get(URL, {"ordering": "founded_year"})

        assert response.status_code == 400
        assert "Allowed" in response.json()["ordering"]

    def test_ties_fall_back_to_name(self, client):
        make_review(make_brand("zeta"), "z", rating=4)

        assert slugs(get(client, ordering="-average_rating"))[1:3] == ["mid", "zeta"]


class TestPagination:
    @pytest.fixture(autouse=True)
    def brands(self):
        for i in range(30):
            make_brand(f"brand-{i:02d}")

    def test_default_page_size_is_12(self, client):
        data = get(client)

        assert len(data["results"]) == 12
        assert data["count"] == 30
        assert data["next"] is not None

    def test_page_and_page_size(self, client):
        data = get(client, page=2, page_size=10)

        assert slugs(data) == [f"brand-{i:02d}" for i in range(10, 20)]
        assert data["previous"] is not None

    def test_page_size_is_capped(self, client):
        assert len(get(client, page_size=500)["results"]) == 30

    def test_page_out_of_range_is_a_404(self, client):
        assert client.get(URL, {"page": 99}).status_code == 404

    def test_tied_brands_are_never_repeated_or_dropped_across_pages(self, client):
        for brand in Brand.objects.all():
            make_review(brand, f"{brand.slug}-r", rating=4)  # every brand ties on rating

        seen = []
        for page in (1, 2, 3):
            seen += slugs(get(client, ordering="-average_rating", page=page, page_size=10))

        assert sorted(seen) == [f"brand-{i:02d}" for i in range(30)]


def test_query_count_is_constant(client, industries, django_assert_max_num_queries):
    for i in range(12):
        brand = make_brand(f"b{i}", [industries["insurance"], industries["telecom"]])
        reviewer = Reviewer.objects.create(display_name=f"R{i}")
        for j in range(3):
            make_review(brand, f"b{i}-r{j}", rating=1 + j, reviewer=reviewer)

    # count, brands, industries, top reviews
    with django_assert_max_num_queries(4):
        data = get(client, industry="insurance", ordering="-average_rating")

    assert len(data["results"]) == 12


class TestHostileInput:
    @pytest.mark.parametrize("value", ["\x00", "a\x00b", "%", "a b", "../x", "ü"])
    def test_an_industry_that_cannot_be_a_slug_is_an_empty_page_not_a_500(self, client, value):
        make_brand("acme")

        response = client.get(URL, {"industry": value})

        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_a_valid_slug_still_matches_alongside_an_invalid_one(self, client, industries):
        make_brand("acme", [industries["insurance"]])

        data = get(client, industry=["insurance", "\x00"])

        assert slugs(data) == ["acme"]

    def test_responses_forbid_framing(self, client, db):
        assert client.get(URL)["X-Frame-Options"] == "DENY"
        assert client.get("/")["X-Frame-Options"] == "DENY"
