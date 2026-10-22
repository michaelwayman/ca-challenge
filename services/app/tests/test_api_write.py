import json
import time

import pytest

from ca_authlib.claims import AUDIENCE_APP, ISSUER, Introspection, Role, issue_claims
from ca_authlib.testing import TestKey
from catalog.models import Brand

from .fake_auth import KEY

pytestmark = pytest.mark.django_db


@pytest.fixture
def brand():
    return Brand.objects.create(slug="acme", name="Acme", description="<p>Old text</p>")


def token(roles=(Role.EDITOR,), **kwargs):
    kwargs.setdefault("audience", AUDIENCE_APP)
    return KEY.sign(
        issue_claims(
            "user-1", roles, kwargs.pop("audience"), kwargs.pop("ttl", 600), now=int(time.time())
        )
    )


def patch(client, body, bearer=None, slug="acme"):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {bearer}"} if bearer else {}
    return client.patch(
        f"/api/brands/{slug}/", json.dumps(body), content_type="application/json", **headers
    )


def stored(brand):
    brand.refresh_from_db()
    return brand.description


class TestPublicRead:
    def test_get_needs_no_token(self, client, brand):
        response = client.get("/api/brands/acme/")

        assert response.status_code == 200
        assert response.json()["description"] == "<p>Old text</p>"

    def test_get_makes_no_calls_to_the_auth_service(self, client, brand, auth_service):
        client.get("/api/brands/acme/")

        assert auth_service.introspection_calls == []

    def test_a_bad_token_on_a_public_read_is_still_a_401(self, client, brand, auth_service):
        response = client.get("/api/brands/acme/", HTTP_AUTHORIZATION="Bearer garbage")

        assert response.status_code == 401

    def test_unknown_brand_is_a_404(self, client, db):
        assert client.get("/api/brands/nope/").status_code == 404


class TestEditing:
    def test_an_editor_can_change_the_description(self, client, brand, auth_service):
        response = patch(client, {"description": "  New text  "}, token())

        assert response.status_code == 200
        assert response.json()["description"] == "New text"
        assert stored(brand) == "New text"

    def test_the_response_is_the_full_listing_row(self, client, brand, auth_service):
        response = patch(client, {"description": "New"}, token())

        assert {"name", "slug", "average_rating", "review_count", "top_review"} <= set(
            response.json()
        )

    def test_the_service_secret_is_sent_to_the_auth_service(self, client, brand, auth_service):
        raw = token()

        patch(client, {"description": "New"}, raw)

        assert auth_service.introspection_calls == [(raw, "dev-service-secret")]

    def test_other_fields_are_rejected_not_ignored(self, client, brand, auth_service):
        response = patch(client, {"description": "New", "name": "Hacked"}, token())

        assert response.status_code == 400
        assert "name" in response.json()
        brand.refresh_from_db()
        assert (brand.name, brand.description) == ("Acme", "<p>Old text</p>")

    @pytest.mark.parametrize(
        "value", ["", "   ", "x" * 20_001, None, 5, "<script>alert(1)</script>"]
    )
    def test_invalid_descriptions_are_a_400(self, client, brand, auth_service, value):
        assert patch(client, {"description": value}, token()).status_code == 400
        assert stored(brand) == "<p>Old text</p>"

    def test_an_empty_patch_is_a_no_op(self, client, brand, auth_service):
        assert patch(client, {}, token()).status_code == 200
        assert stored(brand) == "<p>Old text</p>"

    def test_the_name_and_seo_are_untouched(self, client, auth_service):
        brand = Brand.objects.create(slug="acme", name="Acme", seo={"a": 1})

        patch(client, {"description": "<p>New</p>"}, token())

        brand.refresh_from_db()
        assert (brand.name, brand.seo) == ("Acme", {"a": 1})

    def test_unsafe_markup_is_stripped_before_it_is_stored_and_returned(
        self, client, brand, auth_service
    ):
        unsafe = '<p onclick="x()">Hi <script>alert(1)</script><a href="javascript:x()">y</a></p>'

        response = patch(client, {"description": unsafe}, token())

        assert response.status_code == 200
        for text in (stored(brand), response.json()["description"]):
            assert "<script" not in text
            assert "onclick" not in text
            assert "javascript:" not in text
            assert text.startswith("<p>Hi ")

    def test_the_card_excerpt_is_plain_text(self, client, brand, auth_service):
        response = patch(client, {"description": "<p>Plain <strong>and bold</strong></p>"}, token())

        assert response.json()["excerpt"] == "Plain and bold"

    def test_put_and_delete_are_not_allowed(self, client, brand, auth_service):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token()}"}

        assert (
            client.put(
                "/api/brands/acme/", "{}", content_type="application/json", **headers
            ).status_code
            == 405
        )
        assert client.delete("/api/brands/acme/", **headers).status_code == 405

    def test_unknown_brand_is_a_404(self, client, db, auth_service):
        assert patch(client, {"description": "x"}, token(), slug="nope").status_code == 404


class TestWhoMayEdit:
    def test_no_token_is_a_401(self, client, brand, auth_service):
        response = patch(client, {"description": "New"})

        assert response.status_code == 401
        assert response["WWW-Authenticate"].startswith("Bearer")
        assert stored(brand) == "<p>Old text</p>"

    def test_a_reader_is_a_403(self, client, brand, auth_service):
        auth_service.introspection = Introspection(True, "user-1", ("reader",))

        response = patch(client, {"description": "New"}, token([Role.READER]))

        assert response.status_code == 403
        assert stored(brand) == "<p>Old text</p>"

    @pytest.mark.parametrize(
        "bearer",
        [
            "garbage",
            TestKey("k1").sign(issue_claims("user-1", [Role.EDITOR], AUDIENCE_APP, 600)),  # forged
            TestKey("other").sign(issue_claims("user-1", [Role.EDITOR], AUDIENCE_APP, 600)),
        ],
    )
    def test_a_forged_or_malformed_token_is_a_401(self, client, brand, auth_service, bearer):
        assert patch(client, {"description": "New"}, bearer).status_code == 401
        assert stored(brand) == "<p>Old text</p>"

    def test_an_expired_token_is_a_401(self, client, brand, auth_service):
        expired = KEY.sign(issue_claims("user-1", [Role.EDITOR], AUDIENCE_APP, 60, now=1_000_000))

        assert patch(client, {"description": "New"}, expired).status_code == 401

    def test_a_token_minted_for_another_service_is_a_401(self, client, brand, auth_service):
        assert patch(client, {"description": "New"}, token(audience="elsewhere")).status_code == 401

    def test_a_token_from_another_issuer_is_a_401(self, client, brand, auth_service):
        payload = {
            **{"iss": "evil", "aud": AUDIENCE_APP, "sub": "u", "roles": ["editor"], "v": 1},
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "jti": "x",
        }

        assert patch(client, {"description": "New"}, KEY.sign(payload)).status_code == 401

    def test_a_token_without_a_version_is_a_401(self, client, brand, auth_service):
        payload = {
            "iss": ISSUER,
            "aud": AUDIENCE_APP,
            "sub": "u",
            "roles": ["editor"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "jti": "x",
        }

        assert patch(client, {"description": "New"}, KEY.sign(payload)).status_code == 401


class TestRevocationAndRoleChanges:
    """The token still says editor; the auth service says otherwise."""

    def test_a_demoted_user_is_refused_before_the_token_expires(self, client, brand, auth_service):
        auth_service.introspection = Introspection(True, "user-1", ("reader",))

        response = patch(client, {"description": "New"}, token([Role.EDITOR]))

        assert response.status_code == 403
        assert stored(brand) == "<p>Old text</p>"

    def test_a_disabled_user_is_a_401(self, client, brand, auth_service):
        auth_service.introspection = Introspection(False)

        assert patch(client, {"description": "New"}, token()).status_code == 401
        assert stored(brand) == "<p>Old text</p>"

    def test_a_promoted_user_is_allowed_before_their_next_token(self, client, brand, auth_service):
        auth_service.introspection = Introspection(True, "user-1", ("editor", "reader"))

        assert patch(client, {"description": "New"}, token([Role.READER])).status_code == 200


class TestAuthServiceOutage:
    def test_writes_fail_closed_when_introspection_is_unreachable(
        self, client, brand, auth_service
    ):
        auth_service.introspection_down = True

        response = patch(client, {"description": "New"}, token([Role.EDITOR]))

        assert response.status_code == 503
        assert stored(brand) == "<p>Old text</p>"

    @pytest.mark.parametrize("status", [500, 502, 401, 403])
    def test_an_unhelpful_answer_is_a_503_not_a_decision(self, client, brand, auth_service, status):
        auth_service.introspection_status = status

        assert patch(client, {"description": "New"}, token()).status_code == 503
        assert stored(brand) == "<p>Old text</p>"

    def test_reads_keep_working_through_the_outage(self, client, brand, auth_service):
        auth_service.introspection_down = True
        auth_service.jwks_down = True

        assert client.get("/api/brands/acme/").status_code == 200
        assert client.get("/api/brands/").status_code == 200

    def test_with_cached_keys_a_token_still_verifies_but_the_write_still_fails_closed(
        self, client, brand, auth_service
    ):
        raw = token()
        patch(client, {"description": "First"}, raw)  # warms the key cache
        auth_service.introspection_down = True
        auth_service.jwks_down = True

        response = patch(client, {"description": "Second"}, raw)

        assert response.status_code == 503  # verified locally, then no roles to trust
        assert stored(brand) == "First"

    def test_no_cached_keys_and_no_auth_service_is_a_503(self, client, brand, auth_service):
        auth_service.jwks_down = True

        assert patch(client, {"description": "New"}, token()).status_code == 503


class TestMalformedBodies:
    @pytest.mark.parametrize("body", [[], [{"a": 1}], "text", 5, None, {"description": {"a": 1}}])
    def test_a_body_that_is_not_the_right_shape_is_a_400_never_a_500(
        self, client, brand, auth_service, body
    ):
        assert patch(client, body, token()).status_code == 400
        assert stored(brand) == "<p>Old text</p>"

    def test_a_null_character_is_a_400(self, client, brand, auth_service):
        assert patch(client, {"description": "a\x00b"}, token()).status_code == 400

    def test_invalid_json_is_a_400(self, client, brand, auth_service):
        response = client.patch(
            "/api/brands/acme/",
            "{bad",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token()}",
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "content_type", ["application/x-www-form-urlencoded", "multipart/form-data", "text/plain"]
    )
    def test_only_json_is_accepted(self, client, brand, auth_service, content_type):
        response = client.patch(
            "/api/brands/acme/",
            "description=hi",
            content_type=content_type,
            HTTP_AUTHORIZATION=f"Bearer {token()}",
        )

        assert response.status_code == 415
        assert stored(brand) == "<p>Old text</p>"
