import json
import re
from datetime import timedelta

import pytest
from django.template import Context, Template
from django.utils import timezone

from catalog.models import Brand, Industry, Page, Review, Reviewer

pytestmark = pytest.mark.django_db

NOW = timezone.now()


def make_brand(slug="acme", **kwargs):
    kwargs.setdefault("name", slug.title())
    return Brand.objects.create(slug=slug, **kwargs)


def make_review(brand, slug, rating=5, age_days=0, **kwargs):
    kwargs.setdefault("title", slug.replace("-", " ").title())
    return Review.objects.create(
        slug=slug,
        rating=rating,
        brand=brand,
        published_at=NOW - timedelta(days=age_days),
        **kwargs,
    )


class TestPermalinks:
    def test_brand_and_review_urls_match_wordpress(self):
        brand = make_brand("acme-insurance")
        review = make_review(brand, "smooth-claim")

        assert brand.get_absolute_url() == "/brand/acme-insurance/"
        assert review.get_absolute_url() == "/review/smooth-claim/"

    def test_missing_trailing_slash_redirects(self, client):
        make_brand("acme")

        response = client.get("/brand/acme")

        assert response.status_code == 301
        assert response["Location"] == "/brand/acme/"

    @pytest.mark.parametrize("url", ["/brand/nope/", "/review/nope/"])
    def test_unknown_slug_is_a_404_page(self, client, url):
        response = client.get(url)

        assert response.status_code == 404
        assert "Page not found" in response.content.decode()


class TestHome:
    def test_shows_hero_and_recent_reviews_newest_first(self, client):
        brand = make_brand()
        make_review(brand, "older", age_days=5)
        make_review(brand, "newer", age_days=1)

        html = client.get("/").content.decode()

        assert "Honest reviews of consumer brands" in html
        assert html.index("Newer") < html.index("Older")

    def test_featured_brands_use_the_derived_rating_and_put_unrated_last(self, client):
        low = make_brand("low")
        high = make_brand("high")
        make_brand("unrated")
        make_review(low, "l1", rating=2)
        make_review(high, "h1", rating=5)

        html = client.get("/").content.decode()

        assert (
            html.index("/brand/high/") < html.index("/brand/low/") < html.index("/brand/unrated/")
        )

    def test_limits_recent_reviews_to_six(self, client):
        brand = make_brand()
        for i in range(8):
            make_review(brand, f"review-{i}", age_days=i)

        html = client.get("/").content.decode()

        assert html.count('class="card__title"') == 1 + 6  # one brand card + six reviews

    def test_query_count_does_not_grow_with_data(self, client, django_assert_max_num_queries):
        for i in range(6):
            brand = make_brand(f"b{i}")
            brand.industries.add(Industry.objects.create(name=f"I{i}", slug=f"i{i}"))
            make_review(brand, f"r{i}", reviewer=Reviewer.objects.create(display_name=f"R{i}"))

        with django_assert_max_num_queries(4):
            assert client.get("/").status_code == 200


class TestDescriptionEscaping:
    """Cards show an escaped plain-text excerpt; only the brand page renders the HTML."""

    def test_the_brand_page_renders_the_html_and_the_card_shows_only_text(self, client):
        make_brand("acme", description="<p>About <strong>Acme</strong> &amp; co</p>")

        page = client.get("/brand/acme/").content.decode()
        card = client.get("/brand/").content.decode()

        assert "<p>About <strong>Acme</strong> &amp; co</p>" in page
        assert "About Acme &amp; co" in card
        assert "<strong>Acme</strong>" not in card

    def test_markup_that_got_past_every_write_path_is_still_inert(self, client):
        brand = make_brand("acme", description="<p>fine</p>")
        # update() skips save(), the way a SQL fix-up or a bulk write would.
        Brand.objects.filter(pk=brand.pk).update(
            description="<p>Hi</p><script>alert(1)</script><img src=x onerror=alert(2)>"
        )

        card = client.get("/brand/").content.decode()
        home = client.get("/").content.decode()

        for html in (card, home):
            assert "<script>alert(1)" not in html
            assert "<img src=x" not in html


class TestBrandDetail:
    def test_shows_facts_derived_rating_and_reviews_newest_first(self, client):
        brand = make_brand(
            "acme",
            name="Acme Insurance Co.",
            headquarters="Hartford, CT",
            founded_year=1985,
            website_url="https://acme.example.com",
            description="<p>About Acme</p>",
        )
        brand.industries.add(Industry.objects.create(name="Insurance", slug="insurance"))
        make_review(brand, "old", rating=3, age_days=9, title="Old one")
        make_review(brand, "new", rating=4, age_days=1, title="New one")

        html = client.get("/brand/acme/").content.decode()

        assert "Acme Insurance Co." in html
        assert "Hartford, CT" in html
        assert "1985" in html
        assert "acme.example.com" in html
        assert "<p>About Acme</p>" in html
        assert "Insurance" in html
        assert "(2 reviews)" in html
        assert 'aria-label="Rating: 3.5 out of 5"' in html
        assert "4.9" not in html
        assert html.index("New one") < html.index("Old one")

    def test_brand_without_reviews_says_so(self, client):
        make_brand("acme")

        html = client.get("/brand/acme/").content.decode()

        assert "No reviews yet." in html
        assert "No ratings yet" in html

    def test_seo_title_and_description_are_used(self, client):
        make_brand("acme", seo={"title": "Acme Reviews - Auto", "description": "Read reviews"})

        html = client.get("/brand/acme/").content.decode()

        assert "<title>Acme Reviews - Auto</title>" in html
        assert '<meta name="description" content="Read reviews">' in html

    def test_title_falls_back_to_the_brand_name(self, client):
        make_brand("acme", name="Acme")

        assert "<title>Acme</title>" in client.get("/brand/acme/").content.decode()

    def test_javascript_website_url_is_not_linked(self, client):
        make_brand("acme", website_url="javascript:alert(1)")

        assert "javascript:" not in client.get("/brand/acme/").content.decode()

    def test_user_text_is_escaped_but_stored_html_bodies_render(self, client):
        brand = make_brand("acme")
        make_review(brand, "xss", title="<script>alert(1)</script>", body="<p>ok</p>")

        html = client.get("/brand/acme/").content.decode()

        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
        assert "<p>ok</p>" in html

    def test_query_count_does_not_grow_with_reviews(self, client, django_assert_max_num_queries):
        brand = make_brand("acme")
        for i in range(10):
            make_review(brand, f"r{i}", reviewer=Reviewer.objects.create(display_name=f"R{i}"))

        with django_assert_max_num_queries(4):
            assert client.get("/brand/acme/").status_code == 200


class TestReviewDetail:
    def test_shows_review_with_backlink_and_byline(self, client):
        brand = make_brand("acme", name="Acme")
        reviewer = Reviewer.objects.create(display_name="Sarah K.")
        make_review(
            brand,
            "smooth",
            rating=5,
            title="Smooth claim",
            body="<p>Quick</p>",
            reviewer=reviewer,
            reviewer_location="Albany, NY",
        )

        html = client.get("/review/smooth/").content.decode()

        assert "Smooth claim" in html
        assert 'href="/brand/acme/"' in html
        assert "Sarah K., Albany, NY" in html
        assert "<p>Quick</p>" in html
        assert 'aria-label="Rating: 5.0 out of 5"' in html

    def test_review_without_a_reviewer_still_renders(self, client):
        make_review(make_brand("acme"), "anon", reviewer=None)

        assert client.get("/review/anon/").status_code == 200


class TestStarsTag:
    @staticmethod
    def render(rating, show_value=False):
        template = Template("{% load catalog_extras %}{% stars rating show_value=show_value %}")
        return template.render(Context({"rating": rating, "show_value": show_value}))

    @pytest.mark.parametrize(("rating", "full"), [(3.9, 4), (3.4, 3), (3.5, 4), (0, 0), (5, 5)])
    def test_fills_to_the_nearest_whole_star(self, rating, full):
        assert self.render(rating).count("stars__star--full") == full

    def test_no_rating_renders_a_message_not_empty_stars(self):
        assert "No ratings yet" in self.render(None)


class TestHeroMatchesWordPress:
    """WordPress: gradient hero on the home page and both archives, white hero on a single
    brand or review, none on static pages."""

    @pytest.mark.parametrize(
        ("url", "classes"),
        [
            ("/", 'class="hero"'),
            ("/brand/", 'class="hero hero--compact"'),
            ("/review/", 'class="hero hero--compact"'),
        ],
    )
    def test_home_and_archives_use_the_gradient_hero(self, client, db, url, classes):
        html = client.get(url).content.decode()

        assert f"<section {classes}>" in html
        assert "hero--plain" not in html

    def test_single_brand_and_review_pages_use_the_white_hero(self, client, db):
        brand = make_brand("acme")
        make_review(brand, "one")

        assert 'class="hero hero--plain"' in client.get("/brand/acme/").content.decode()
        assert 'class="hero hero--plain"' in client.get("/review/one/").content.decode()

    def test_static_pages_have_no_hero(self, client, db):
        Page.objects.create(slug="about", title="About", body="")

        assert 'class="hero' not in client.get("/about/").content.decode()


class TestBrandListPage:
    def test_hosts_the_component_with_its_configuration(self, client):
        html = client.get("/brand/").content.decode()

        assert '<div id="brand-list"' in html
        assert 'data-api-url="/api/brands/"' in html
        assert 'data-industries-id="brand-list-industries"' in html
        assert '<script type="module" src="/static/js/brand-list.js">' in html

    def test_passes_every_industry_as_json_for_the_filter_with_its_brand_count(self, client):
        telecom = Industry.objects.create(name="Telecom", slug="telecom")
        Industry.objects.create(name="Insurance", slug="insurance")
        make_brand("swift").industries.add(telecom)
        make_brand("wave").industries.add(telecom)

        html = client.get("/brand/").content.decode()

        match = re.search(
            r'<script id="brand-list-industries" type="application/json">(.*?)</script>', html
        )
        assert json.loads(match.group(1)) == [
            {"name": "Insurance", "slug": "insurance", "brand_count": 0},
            {"name": "Telecom", "slug": "telecom", "brand_count": 2},
        ]

    def test_industries_are_listed_alphabetically_whatever_order_they_were_created_in(self, client):
        for name in ["Telecom", "Finance", "Retail", "Insurance"]:
            Industry.objects.create(name=name, slug=name.lower())

        html = client.get("/brand/").content.decode()

        match = re.search(
            r'<script id="brand-list-industries" type="application/json">(.*?)</script>', html
        )
        names = [i["name"] for i in json.loads(match.group(1))]
        assert names == ["Finance", "Insurance", "Retail", "Telecom"]

    def test_industry_json_cannot_break_out_of_its_script_tag(self, client):
        Industry.objects.create(name="</script><b>x", slug="evil")

        html = client.get("/brand/").content.decode()

        assert "</script><b>" not in html

    def test_lists_brands_for_visitors_without_javascript(self, client):
        make_brand("acme", name="Acme Insurance")

        html = client.get("/brand/").content.decode()

        assert "<noscript>" in html
        assert "Acme Insurance" in html

    def test_query_count_does_not_grow_with_brands(self, client, django_assert_max_num_queries):
        for i in range(8):
            brand = make_brand(f"b{i}")
            brand.industries.add(Industry.objects.create(name=f"I{i}", slug=f"i{i}"))
            make_review(brand, f"r{i}")

        with django_assert_max_num_queries(4):
            assert client.get("/brand/").status_code == 200


class TestNav:
    @pytest.mark.parametrize(("url", "current"), [("/", "Home"), ("/brand/", "Brands")])
    def test_marks_the_current_page(self, client, url, current):
        html = client.get(url).content.decode()

        marked = re.findall(
            r'<a class="site-nav__link"[^>]*aria-current="page"[^>]*>(\w+)</a>', html
        )
        assert marked == [current]

    def test_marks_nothing_on_a_detail_page(self, client):
        make_brand("acme")

        assert 'aria-current="page"' not in client.get("/brand/acme/").content.decode()

    def test_home_links_to_the_brand_list(self, client):
        assert 'href="/brand/"' in client.get("/").content.decode()


def test_a_host_build_comes_before_the_images_assets(settings):
    # static/ is listed even if it is missing at startup, so `make css-watch` works on a
    # running server; the image's copy (ASSETS_DIR) is the fallback behind it.
    assert settings.STATICFILES_DIRS[0].name == "static"
    assert "staticfiles.W004" in settings.SILENCED_SYSTEM_CHECKS


class TestExcerptEncoding:
    def test_entities_in_a_review_body_are_not_double_escaped_on_the_homepage(self, client):
        make_review(make_brand("acme"), "amp", body="<p>Fish &amp; chips &lt;3 for $5</p>")

        html = client.get("/").content.decode()

        assert "Fish &amp; chips &lt;3 for $5" in html
        assert "&amp;amp;" not in html


def make_reviews(brand, count, **kwargs):
    for i in range(count):
        make_review(brand, f"review-{i:02d}", age_days=i, **kwargs)  # review-00 is the newest


class TestReviewList:
    def test_first_page_has_the_ten_newest_reviews_newest_first(self, client):
        make_reviews(make_brand("acme"), 25)

        response = client.get("/review/")
        html = response.content.decode()

        assert response.status_code == 200
        assert "All Reviews" in html
        assert html.count('class="review"') == 10
        assert html.index("Review 00") < html.index("Review 09")
        assert "Review 10" not in html

    def test_later_pages_continue_the_list(self, client):
        make_reviews(make_brand("acme"), 25)

        html = client.get("/review/page/3/").content.decode()

        assert html.count('class="review"') == 5
        assert "Review 20" in html
        assert "Review 24" in html

    def test_page_one_by_its_long_url_redirects_to_the_canonical_one(self, client):
        make_reviews(make_brand("acme"), 15)

        response = client.get("/review/page/1/")

        assert response.status_code == 301
        assert response["Location"] == "/review/"

    @pytest.mark.parametrize("url", ["/review/page/0/", "/review/page/3/", "/review/page/abc/"])
    def test_pages_that_do_not_exist_are_a_404(self, client, url):
        make_reviews(make_brand("acme"), 15)  # two pages

        assert client.get(url).status_code == 404

    def test_an_empty_archive_says_so_and_has_no_pagination(self, client, db):
        html = client.get("/review/").content.decode()

        assert "No reviews yet." in html
        assert "Pagination" not in html

    def test_a_single_page_has_no_pagination(self, client):
        make_reviews(make_brand("acme"), 10)

        assert "Pagination" not in client.get("/review/").content.decode()

    def test_each_row_links_to_its_brand_and_review_and_shows_the_byline(self, client):
        brand = make_brand("acme", name="Acme Insurance")
        reviewer = Reviewer.objects.create(display_name="Sarah K.")
        make_review(
            brand,
            "smooth",
            rating=4,
            title="Smooth claim",
            reviewer=reviewer,
            reviewer_location="Albany, NY",
            body="<p>Quick and painless.</p>",
        )

        html = client.get("/review/").content.decode()

        assert 'href="/brand/acme/"' in html
        assert 'href="/review/smooth/"' in html
        assert "Acme Insurance" in html
        assert 'aria-label="Rating: 4.0 out of 5"' in html
        assert "Sarah K., Albany, NY" in html
        assert "Quick and painless." in html

    def test_the_excerpt_is_plain_text_cut_at_forty_words(self, client):
        words = " ".join(f"w{i}" for i in range(60))
        make_review(make_brand("acme"), "long", body=f"<p><b>{words}</b></p><p>tail &amp; more</p>")

        html = client.get("/review/").content.decode()

        assert "w39" in html
        assert "w40" not in html
        assert "<b>" not in html
        assert "…" in html

    def test_entities_are_encoded_once(self, client):
        make_review(make_brand("acme"), "amp", body="<p>I had AT&amp;T before</p>")

        html = client.get("/review/").content.decode()

        assert "AT&amp;T before" in html
        assert "&amp;amp;" not in html

    def test_titles_and_brand_names_are_escaped(self, client):
        make_review(make_brand("acme", name="<b>Acme</b>"), "x", title="<script>alert(1)</script>")

        html = client.get("/review/").content.decode()

        assert "<script>alert(1)</script>" not in html
        assert "&lt;b&gt;Acme&lt;/b&gt;" in html

    def test_the_page_title_names_the_page_number(self, client):
        make_reviews(make_brand("acme"), 15)

        assert (
            "<title>Reviews Archive | Brand Reviews</title>"
            in client.get("/review/").content.decode()
        )
        assert "(page 2)" in client.get("/review/page/2/").content.decode()

    def test_query_count_does_not_grow_with_the_page(self, client, django_assert_max_num_queries):
        brand = make_brand("acme")
        for i in range(10):
            make_review(brand, f"r{i}", reviewer=Reviewer.objects.create(display_name=f"R{i}"))

        with django_assert_max_num_queries(3):  # count, the page (joined), nothing per row
            assert client.get("/review/").status_code == 200


class TestReviewPagination:
    @pytest.fixture(autouse=True)
    def reviews(self):
        make_reviews(make_brand("acme"), 60)  # six pages

    @staticmethod
    def links(html):
        return re.findall(r'<a class="pagination__link[^"]*" href="([^"]+)"[^>]*>([^<]+)</a>', html)

    def test_the_first_page_disables_previous_and_marks_page_one_current(self, client):
        html = client.get("/review/").content.decode()

        assert 'aria-disabled="true">Previous</span>' in html
        assert re.search(r'pagination__link--current" href="/review/" aria-current="page">1<', html)
        assert ("/review/page/2/", "Next") in self.links(html)

    def test_a_middle_page_links_both_ways(self, client):
        links = self.links(client.get("/review/page/4/").content.decode())

        assert ("/review/page/3/", "Previous") in links
        assert ("/review/page/5/", "Next") in links

    def test_many_pages_collapse_to_the_ends_and_the_neighbours_of_the_current_page(self, client):
        brand = Brand.objects.get(slug="acme")
        for i in range(40):  # 100 reviews, ten pages
            make_review(brand, f"extra-{i}", age_days=100 + i)

        html = client.get("/review/page/5/").content.decode()

        numbers = [text for _, text in self.links(html) if text.isdigit()]
        assert numbers == ["1", "4", "5", "6", "10"]
        assert html.count("pagination__gap") == 2

    def test_previous_from_page_two_goes_to_the_canonical_first_page(self, client):
        links = self.links(client.get("/review/page/2/").content.decode())

        assert ("/review/", "Previous") in links
        assert ("/review/", "1") in links

    def test_the_last_page_disables_next(self, client):
        html = client.get("/review/page/6/").content.decode()

        assert 'aria-disabled="true">Next</span>' in html

    def test_exactly_one_link_is_the_current_page(self, client):
        html = client.get("/review/page/3/").content.decode()

        assert html.count('aria-current="page"') == 2  # the nav's Reviews link and page 3


class TestStaticPages:
    @pytest.fixture
    def about(self, db):
        return Page.objects.create(
            slug="about", title="About", body="<p>We collect <b>honest</b> reviews.</p>"
        )

    def test_a_page_is_served_at_its_slug(self, client, about):
        response = client.get("/about/")
        html = response.content.decode()

        assert response.status_code == 200
        assert "<h1" in html and "About</h1>" in html
        assert "<p>We collect <b>honest</b> reviews.</p>" in html
        assert "<title>About | Brand Reviews</title>" in html

    def test_a_missing_trailing_slash_redirects(self, client, about):
        response = client.get("/about")

        assert response.status_code == 301
        assert response["Location"] == "/about/"

    def test_an_unknown_page_is_a_404(self, client, about):
        assert client.get("/nope/").status_code == 404

    def test_the_title_is_escaped_but_the_stored_body_renders(self, client, db):
        Page.objects.create(slug="x", title="<script>alert(1)</script>", body="<p>ok</p>")

        html = client.get("/x/").content.decode()

        assert "<script>alert(1)</script>" not in html
        assert "<p>ok</p>" in html

    @pytest.mark.parametrize("slug", ["brand", "review"])
    def test_a_page_can_never_shadow_a_real_route(self, client, db, slug):
        Page.objects.create(slug=slug, title="Impostor", body="<p>nope</p>")

        assert "Impostor" not in client.get(f"/{slug}/").content.decode()

    def test_the_page_knows_its_url(self, about):
        assert about.get_absolute_url() == "/about/"


class TestNavWithEveryPage:
    def test_the_nav_lists_all_four_pages_in_order(self, client, db):
        html = client.get("/").content.decode()

        links = re.findall(r'<a class="site-nav__link" href="([^"]+)"', html)
        assert links == ["/", "/brand/", "/review/", "/about/"]

    @pytest.mark.parametrize(
        ("url", "current"),
        [("/review/", "Reviews"), ("/review/page/2/", "Reviews"), ("/about/", "About")],
    )
    def test_marks_the_current_page(self, client, db, url, current):
        make_reviews(make_brand("acme"), 15)
        Page.objects.create(slug="about", title="About", body="")

        html = client.get(url).content.decode()

        marked = re.findall(
            r'<a class="site-nav__link"[^>]*aria-current="page"[^>]*>(\w+)</a>', html
        )
        assert marked == [current]

    def test_a_single_review_does_not_mark_the_archive_as_current(self, client, db):
        make_review(make_brand("acme"), "one")

        assert 'aria-current="page"' not in client.get("/review/one/").content.decode()

    def test_the_homepage_links_to_the_archive(self, client, db):
        assert 'class="section__link" href="/review/"' in client.get("/").content.decode()


class TestExcerptFilter:
    @staticmethod
    def render(body, words=3):
        template = Template("{% load catalog_extras %}{{ body|excerpt:words }}")
        return template.render(Context({"body": body, "words": words}))

    def test_cuts_at_the_word_count_with_an_ellipsis(self):
        assert self.render("<p>one two three four five</p>") == "one two three…"

    def test_short_text_is_unchanged(self):
        assert self.render("<p>one two</p>") == "one two"

    def test_tags_become_spaces_between_paragraphs(self):
        assert self.render("<p>one</p><p>two</p>") == "one two"

    def test_entities_are_encoded_exactly_once(self):
        assert self.render("<p>AT&amp;T &lt;b&gt;</p>", words=5) == "AT&amp;T &lt;b&gt;"
