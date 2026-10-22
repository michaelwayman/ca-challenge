from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.utils import timezone

from catalog.models import Brand, Industry, Page, Review, Reviewer

pytestmark = pytest.mark.django_db

EDITOR_SUB = "11111111-1111-4111-8111-111111111111"
LOGIN = "/admin/login/"


@pytest.fixture
def signed_in(auth_service, client):
    """A client signed in to the admin as an editor, through the (fake) auth service."""
    auth_service.add_account("ed", "pw", ["editor", "reader"], sub=EDITOR_SUB)
    assert client.login(username="ed", password="pw")
    return client


def post_login(client, username, password):
    return client.post(LOGIN, {"username": username, "password": password, "next": "/admin/"})


def make_brand(slug="acme", **kwargs):
    kwargs.setdefault("name", slug.title())
    return Brand.objects.create(slug=slug, **kwargs)


def make_review(brand, slug="r1", **kwargs):
    kwargs.setdefault("title", slug.title())
    kwargs.setdefault("rating", 4)
    kwargs.setdefault("published_at", timezone.now() - timedelta(days=1))
    return Review.objects.create(slug=slug, brand=brand, **kwargs)


class TestSignIn:
    def test_anonymous_visitors_are_sent_to_the_login_page(self, client):
        response = client.get("/admin/")

        assert response.status_code == 302
        assert response["Location"] == "/admin/login/?next=/admin/"

    def test_an_editor_signs_in_with_their_auth_service_password(self, client, auth_service):
        auth_service.add_account("ed", "pw", ["editor", "reader"], sub=EDITOR_SUB)

        response = post_login(client, "ed", "pw")

        assert response.status_code == 302
        assert response["Location"] == "/admin/"
        assert "Brand Reviews admin" in client.get("/admin/").content.decode()
        assert auth_service.token_calls == [("ed", "pw")]

    def test_a_reader_is_refused_even_with_the_right_password(self, client, auth_service):
        auth_service.add_account(
            "sarah", "pw", ["reader"], sub="22222222-2222-4222-8222-222222222222"
        )

        response = post_login(client, "sarah", "pw")

        assert response.status_code == 200
        assert "staff account" in response.content.decode()
        assert not User.objects.exists()  # a non-editor never gets a local row

    @pytest.mark.parametrize(
        "problem",
        ["wrong_password", "auth_down", "wrong_audience", "keys_down"],
    )
    def test_every_way_sign_in_can_fail_is_just_a_refusal_never_an_error(
        self, client, auth_service, problem
    ):
        auth_service.add_account("ed", "pw", ["editor"], sub=EDITOR_SUB)
        password = "wrong" if problem == "wrong_password" else "pw"
        auth_service.token_down = problem == "auth_down"
        auth_service.jwks_down = problem == "keys_down"
        if problem == "wrong_audience":
            auth_service.token_audience = "some-other-service"

        response = post_login(client, "ed", password)

        assert response.status_code == 200
        assert "staff account" in response.content.decode()
        assert client.get("/admin/").status_code == 302

    def test_the_local_row_holds_no_password_and_is_keyed_by_the_auth_service_id(
        self, client, auth_service
    ):
        auth_service.add_account("ed", "pw", ["editor"], sub=EDITOR_SUB)

        post_login(client, "ed", "pw")

        user = User.objects.get(username=EDITOR_SUB)
        assert not user.has_usable_password()
        assert (user.is_staff, user.is_superuser, user.is_active) == (True, True, True)
        assert user.first_name == "ed"

    def test_signing_in_again_reuses_the_same_row(self, client, auth_service):
        auth_service.add_account("ed", "pw", ["editor"], sub=EDITOR_SUB)

        post_login(client, "ed", "pw")
        client.logout()
        post_login(client, "ed", "pw")

        assert User.objects.count() == 1

    def test_the_local_row_cannot_be_signed_in_with_a_local_password(self, signed_in):
        # The only way in is the auth service; the row's own password is unusable.
        assert authenticate(username=EDITOR_SUB, password="") is None
        assert authenticate(username=EDITOR_SUB, password="pw") is None

    def test_a_demoted_editor_loses_access_at_their_next_sign_in_attempt(
        self, signed_in, auth_service, client_class=None
    ):
        from django.test import Client

        auth_service.accounts["ed"]["roles"] = ["reader"]
        other_browser = Client()

        assert post_login(other_browser, "ed", "pw").status_code == 200  # refused now

        assert User.objects.get(username=EDITOR_SUB).is_staff is False
        assert signed_in.get("/admin/").status_code == 302  # and the old session no longer works

    def test_a_failed_check_does_not_demote_anyone(self, signed_in, auth_service):
        from django.test import Client

        auth_service.token_down = True

        post_login(Client(), "ed", "pw")

        assert User.objects.get(username=EDITOR_SUB).is_staff is True

    def test_the_admin_has_its_own_cookie_names_and_a_one_hour_session(self, client, auth_service):
        auth_service.add_account("ed", "pw", ["editor"], sub=EDITOR_SUB)

        response = post_login(client, "ed", "pw")

        assert "app_sessionid" in response.cookies
        assert "sessionid" not in response.cookies
        assert settings.CSRF_COOKIE_NAME == "app_csrftoken"
        assert settings.SESSION_COOKIE_AGE == 3600

    def test_djangos_own_user_and_group_admin_is_switched_off(self, signed_in):
        assert not admin.site.is_registered(User)
        assert not admin.site.is_registered(Group)
        assert signed_in.get("/admin/auth/user/").status_code == 404

    def test_the_json_api_still_works_without_a_csrf_token(self, auth_service):
        from django.test import Client

        make_brand("acme", description="<p>Old</p>")
        strict = Client(enforce_csrf_checks=True)

        assert strict.get("/api/brands/").status_code == 200


class TestEveryModelHasAPage:
    @pytest.mark.parametrize("model", ["industry", "brand", "reviewer", "review", "page"])
    def test_the_changelist_and_add_page_render(self, signed_in, model):
        assert signed_in.get(f"/admin/catalog/{model}/").status_code == 200
        assert signed_in.get(f"/admin/catalog/{model}/add/").status_code == 200

    def test_the_index_lists_all_five_and_nothing_from_djangos_auth_app(self, signed_in):
        html = signed_in.get("/admin/").content.decode()

        for label in ["Industries", "Brands", "Reviewers", "Reviews", "Pages"]:
            assert label in html
        assert "Authentication and Authorization" not in html


class TestIndustryAdmin:
    def test_shows_how_many_brands_each_industry_has(self, signed_in):
        telecom = Industry.objects.create(name="Telecom", slug="telecom")
        make_brand("a").industries.add(telecom)
        make_brand("b").industries.add(telecom)
        Industry.objects.create(name="Retail", slug="retail")

        response = signed_in.get("/admin/catalog/industry/")

        counts = {i.name: i._brand_count for i in response.context["cl"].result_list}
        assert counts == {"Retail": 0, "Telecom": 2}

    def test_adds_an_industry(self, signed_in):
        response = signed_in.post(
            "/admin/catalog/industry/add/", {"name": "Energy", "slug": "energy"}
        )

        assert response.status_code == 302
        assert Industry.objects.filter(slug="energy").exists()


class TestBrandAdmin:
    def test_the_changelist_shows_the_derived_rating_review_count_and_industries(self, signed_in):
        brand = make_brand("acme")
        brand.industries.add(Industry.objects.create(name="Insurance", slug="insurance"))
        make_review(brand, "a", rating=5)
        make_review(brand, "b", rating=2)

        response = signed_in.get("/admin/catalog/brand/")

        [row] = response.context["cl"].result_list
        assert (row.average_rating, row.review_count) == (Decimal("3.5"), 2)  # derived
        html = response.content.decode()
        assert "3.5" in html and "Insurance" in html

    def test_searches_and_filters_by_industry(self, signed_in):
        insurance = Industry.objects.create(name="Insurance", slug="insurance")
        make_brand("acme", name="Acme Insurance").industries.add(insurance)
        make_brand("swift", name="SwiftStream")

        def names(query):
            response = signed_in.get(f"/admin/catalog/brand/?{query}")
            return {b.name for b in response.context["cl"].result_list}

        assert names("q=swift") == {"SwiftStream"}
        assert names(f"industries__id__exact={insurance.pk}") == {"Acme Insurance"}

    def test_sorts_by_the_derived_columns(self, signed_in):
        make_review(make_brand("low"), "l", rating=2)
        make_review(make_brand("high"), "h", rating=5)

        response = signed_in.get("/admin/catalog/brand/?o=4.-1")  # rating, descending

        assert response.status_code == 200

    def test_adding_a_brand_strips_scripts_and_javascript_links_from_the_description(
        self, signed_in
    ):
        dirty = '<p>Hi</p><script>alert(1)</script><a href="javascript:x" onclick="y()">z</a>'

        response = signed_in.post(
            "/admin/catalog/brand/add/", {"name": "New", "slug": "new", "description": dirty}
        )

        assert response.status_code == 302
        description = Brand.objects.get(slug="new").description
        assert "<script" not in description
        assert "javascript:" not in description
        assert "onclick" not in description
        assert "<p>Hi</p>" in description

    def test_editing_keeps_the_site_safe_to_render(self, signed_in):
        brand = make_brand("acme")

        signed_in.post(
            f"/admin/catalog/brand/{brand.pk}/change/",
            {
                "name": "Acme",
                "slug": "acme",
                "description": "<p>ok</p><img src=x onerror=alert(1)>",
            },
        )

        page = signed_in.get("/brand/acme/").content.decode()
        assert "onerror" not in page
        assert "<p>ok</p>" in page

    def test_a_website_typed_without_a_scheme_becomes_https(self, signed_in):
        signed_in.post(
            "/admin/catalog/brand/add/",
            {"name": "New", "slug": "new", "website_url": "example.com/about"},
        )

        assert Brand.objects.get(slug="new").website_url == "https://example.com/about"

    def test_a_non_web_website_is_refused(self, signed_in):
        response = signed_in.post(
            "/admin/catalog/brand/add/",
            {"name": "New", "slug": "new", "website_url": "javascript:alert(1)"},
        )

        assert response.status_code == 200
        assert not Brand.objects.filter(slug="new").exists()

    def test_the_import_fields_are_read_only(self, signed_in):
        brand = make_brand("acme", wp_id=7)

        response = signed_in.get(f"/admin/catalog/brand/{brand.pk}/change/")
        form = response.context["adminform"].form

        assert "wp_id" not in form.fields
        assert "import_wordpress" in response.content.decode()  # the note about re-imports

        signed_in.post(
            f"/admin/catalog/brand/{brand.pk}/change/",
            {"name": "Acme", "slug": "acme", "wp_id": 999},
        )
        assert Brand.objects.get(pk=brand.pk).wp_id == 7


class TestReviewerAdmin:
    def test_the_auth_service_link_is_not_editable(self, signed_in):
        import uuid

        link = uuid.uuid4()
        reviewer = Reviewer.objects.create(display_name="Sarah K.", auth_user_id=link, wp_id=2)

        response = signed_in.get(f"/admin/catalog/reviewer/{reviewer.pk}/change/")
        assert "auth_user_id" not in response.context["adminform"].form.fields

        signed_in.post(
            f"/admin/catalog/reviewer/{reviewer.pk}/change/",
            {"display_name": "Sarah Kay", "auth_user_id": str(uuid.uuid4())},
        )
        reviewer.refresh_from_db()
        assert (reviewer.display_name, reviewer.auth_user_id) == ("Sarah Kay", link)

    def test_shows_each_reviewers_review_count(self, signed_in):
        reviewer = Reviewer.objects.create(display_name="Sarah K.")
        brand = make_brand()
        make_review(brand, "a", reviewer=reviewer)
        make_review(brand, "b", reviewer=reviewer)

        response = signed_in.get("/admin/catalog/reviewer/")

        assert [r._review_count for r in response.context["cl"].result_list] == [2]


class TestReviewAdmin:
    def data(self, brand, **overrides):
        data = {
            "title": "Great",
            "slug": "great",
            "brand": brand.pk,
            "rating": 5,
            "published_at_0": "2026-05-19",
            "published_at_1": "12:00:00",
            "body": "<p>Nice</p>",
            "reviewer_location": "Albany, NY",
        }
        return {**data, **overrides}

    def test_adds_a_review_and_cleans_its_body(self, signed_in):
        brand = make_brand()

        response = signed_in.post(
            "/admin/catalog/review/add/",
            self.data(brand, body="<p>Nice</p><script>alert(1)</script>"),
        )

        assert response.status_code == 302
        review = Review.objects.get(slug="great")
        assert "<script" not in review.body
        assert "<p>Nice</p>" in review.body

    @pytest.mark.parametrize("rating", [0, 6])
    def test_a_rating_outside_one_to_five_is_rejected_with_a_message(self, signed_in, rating):
        brand = make_brand()

        response = signed_in.post("/admin/catalog/review/add/", self.data(brand, rating=rating))

        assert response.status_code == 200
        assert not Review.objects.exists()

    def test_the_brand_picker_searches_as_you_type(self, signed_in):
        make_brand("acme", name="Acme Insurance")
        make_brand("swift", name="SwiftStream")

        response = signed_in.get(
            "/admin/autocomplete/?term=acme&app_label=catalog&model_name=review&field_name=brand"
        )

        assert response.status_code == 200
        assert [r["text"] for r in response.json()["results"]] == ["Acme Insurance"]

    def test_filters_and_searches(self, signed_in):
        acme, swift = (
            make_brand("acme", name="Acme Insurance"),
            make_brand("swift", name="SwiftStream"),
        )
        make_review(acme, "a", rating=5, title="Smooth")
        make_review(swift, "b", rating=2, title="Slow")

        def titles(query):
            response = signed_in.get(f"/admin/catalog/review/?{query}")
            return {r.title for r in response.context["cl"].result_list}

        assert titles("rating__exact=5") == {"Smooth"}
        assert titles("q=SwiftStream") == {"Slow"}
        assert titles("q=smooth") == {"Smooth"}

    def test_the_list_does_not_query_per_row(self, signed_in, django_assert_max_num_queries):
        brand = make_brand()
        for i in range(10):
            make_review(brand, f"r{i}", reviewer=Reviewer.objects.create(display_name=f"R{i}"))

        with django_assert_max_num_queries(12):  # fixed overhead (session, filters), not 10 more
            assert signed_in.get("/admin/catalog/review/").status_code == 200


class TestPageAdmin:
    def test_a_page_added_in_the_admin_is_live_on_the_site(self, signed_in):
        response = signed_in.post(
            "/admin/catalog/page/add/",
            {"title": "Press", "slug": "press", "body": "<p>Hello</p><script>x</script>"},
        )

        assert response.status_code == 302
        live = signed_in.get("/press/")
        assert live.status_code == 200
        assert "<p>Hello</p>" in live.content.decode()
        assert "<script>x" not in live.content.decode()

    @pytest.mark.parametrize("slug", ["brand", "review", "admin", "api"])
    def test_a_slug_that_would_shadow_a_route_is_refused(self, signed_in, slug):
        response = signed_in.post(
            "/admin/catalog/page/add/", {"title": "Impostor", "slug": slug, "body": ""}
        )

        assert response.status_code == 200
        assert "is a route of the site" in response.content.decode()
        assert not Page.objects.filter(slug=slug).exists()


def test_no_model_change_is_missing_a_migration():
    call_command("makemigrations", "--check", "--dry-run")  # exits non-zero if one is missing
