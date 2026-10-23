import json
import time

import pytest

from accounts import keys
from accounts.models import RefreshToken, User
from shared.auth.claims import AUDIENCE_APP, ISSUER
from shared.auth.errors import TokenError

from .conftest import PASSWORD, login, post

pytestmark = pytest.mark.django_db


class TestLogin:
    def test_returns_an_access_token_that_the_shared_library_verifies(
        self, api, make_user, verifier
    ):
        user = make_user(roles=("reader", "editor"))

        body = login(api).json()

        claims = verifier.verify(body["access_token"])
        assert claims.sub == str(user.id)
        assert claims.roles == ("editor", "reader")
        assert (claims.iss, claims.aud) == (ISSUER, AUDIENCE_APP)
        assert 590 <= claims.exp - int(time.time()) <= 600
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 600
        assert body["refresh_token"]

    def test_the_token_names_its_signing_key(self, api, make_user):
        make_user()
        import jwt

        header = jwt.get_unverified_header(login(api).json()["access_token"])

        assert header["alg"] == "EdDSA"
        assert header["kid"] == keys.jwks_document()["keys"][0]["kid"]

    @pytest.mark.parametrize(
        "credentials",
        [
            {"username": "sarah", "password": "wrong"},
            {"username": "nobody", "password": PASSWORD},
        ],
    )
    def test_bad_credentials_get_the_same_401(self, api, make_user, credentials):
        make_user()

        response = login(api, **credentials)

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials."}

    def test_a_disabled_user_cannot_log_in(self, api, make_user):
        make_user(is_active=False)

        assert login(api).status_code == 401

    def test_an_unusable_password_cannot_log_in(self, api, make_user):
        make_user(password=None)

        assert login(api, password="anything").status_code == 401

    def test_missing_fields_are_a_400(self, api):
        assert post(api, "/api/auth/v1/token/", username="x").status_code == 400

    def test_an_unknown_audience_is_a_400(self, api, make_user):
        make_user()

        response = login(api, audience="somebody-else")

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "body",
        [
            {"username": ["a"], "password": {"b": 1}},
            {"username": "a" * 151, "password": "x"},
            {"username": "sarah", "password": "p" * 1025},
            {"username": "sarah\x00", "password": "x"},
        ],
    )
    def test_malformed_or_oversized_credentials_are_a_400(self, api, make_user, body):
        make_user()

        assert post(api, "/api/auth/v1/token/", **body).status_code == 400

    @pytest.mark.parametrize("payload", [[], "x", 5])
    def test_a_body_that_is_not_an_object_is_a_400(self, api, db, payload):
        assert (
            api.post(
                "/api/auth/v1/token/", json.dumps(payload), content_type="application/json"
            ).status_code
            == 400
        )

    def test_form_encoded_bodies_are_refused(self, api, make_user):
        make_user()

        response = api.post("/api/auth/v1/token/", {"username": "sarah", "password": PASSWORD})

        assert response.status_code == 415

    def test_responses_forbid_framing(self, api, db):
        assert api.get("/.well-known/jwks.json")["X-Frame-Options"] == "DENY"

    def test_only_post_is_allowed(self, api):
        assert api.get("/api/auth/v1/token/").status_code == 405

    def test_the_password_is_stored_hashed(self, make_user, settings):
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
        user = make_user()

        assert user.password != PASSWORD
        assert user.password.startswith("pbkdf2_")


class TestTokenFormat:
    def test_the_token_carries_no_version_claim(self, api, make_user):
        import jwt

        make_user()
        token = login(api).json()["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})

        assert "v" not in payload
        assert {"sub", "roles", "iss", "aud", "iat", "exp", "jti"} <= set(payload)


class TestJWKS:
    def test_publishes_the_public_key_only(self, api, db):
        document = api.get("/.well-known/jwks.json").json()

        [key] = document["keys"]
        assert key["kty"] == "OKP"
        assert key["crv"] == "Ed25519"
        assert "d" not in key  # no private material
        assert key["kid"]

    def test_is_cacheable(self, api, db):
        assert "max-age" in api.get("/.well-known/jwks.json")["Cache-Control"]


class TestKeyRotation:
    def test_old_tokens_still_verify_and_new_ones_use_the_new_key(self, api, make_user, verifier):
        make_user()
        old_token = login(api).json()["access_token"]
        old_kid = keys.active_key().kid

        new_kid = keys.create_key().kid
        new_token = login(api).json()["access_token"]

        import jwt

        assert jwt.get_unverified_header(new_token)["kid"] == new_kid != old_kid
        assert verifier.verify(old_token)
        assert verifier.verify(new_token)
        assert {k["kid"] for k in keys.jwks_document()["keys"]} == {old_kid, new_kid}

    def test_a_retired_key_stops_verifying(self, api, make_user, verifier):
        from datetime import timedelta

        from django.utils import timezone

        make_user()
        old_token = login(api).json()["access_token"]
        keys.create_key()
        later = timezone.now() + timedelta(seconds=601)

        assert keys.retire_old_keys(now=later) == 1

        with pytest.raises(TokenError):
            verifier.verify(old_token)

    def test_a_key_is_not_retired_before_its_tokens_have_expired(self, db):
        keys.active_key()
        keys.create_key()

        assert keys.retire_old_keys() == 0


class TestRefresh:
    def refresh(self, api, token):
        return post(api, "/api/auth/v1/refresh/", refresh_token=token)

    def test_returns_a_new_pair_and_the_old_refresh_token_dies(self, api, make_user, verifier):
        make_user()
        first = login(api).json()

        second = self.refresh(api, first["refresh_token"])

        assert second.status_code == 200
        assert verifier.verify(second.json()["access_token"])
        assert second.json()["refresh_token"] != first["refresh_token"]
        assert self.refresh(api, first["refresh_token"]).status_code == 401  # single use

    def test_the_new_access_token_reflects_the_current_roles(self, api, make_user, verifier):
        user = make_user(roles=("reader", "editor"))
        pair = login(api).json()
        user.roles.set(user.roles.filter(name="reader"))

        refreshed = self.refresh(api, pair["refresh_token"]).json()

        assert verifier.verify(refreshed["access_token"]).roles == ("reader",)

    def test_a_disabled_user_cannot_refresh(self, api, make_user):
        user = make_user()
        pair = login(api).json()
        User.objects.filter(pk=user.pk).update(is_active=False)

        assert self.refresh(api, pair["refresh_token"]).status_code == 401

    def test_an_expired_refresh_token_is_rejected(self, api, make_user):
        from datetime import timedelta

        from django.utils import timezone

        make_user()
        pair = login(api).json()
        RefreshToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        assert self.refresh(api, pair["refresh_token"]).status_code == 401

    @pytest.mark.parametrize("token", ["", "nope", "a" * 200])
    def test_garbage_is_rejected(self, api, db, token):
        assert self.refresh(api, token).status_code in (400, 401)

    def test_only_a_hash_is_stored(self, api, make_user):
        make_user()
        pair = login(api).json()

        assert pair["refresh_token"] not in RefreshToken.objects.get().token_hash


def test_the_roles_in_the_database_are_exactly_the_roles_the_library_defines(db):
    from accounts.models import Role
    from shared.auth.claims import Role as LibraryRole

    assert set(Role.objects.values_list("name", flat=True)) == {r.value for r in LibraryRole}
