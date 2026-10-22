import pytest

from accounts import keys
from accounts.models import User
from ca_authlib.claims import AUDIENCE_APP, Introspection, Role, encode_claims, issue_claims
from ca_authlib.testing import TestKey

from .conftest import login

pytestmark = pytest.mark.django_db

URL = "/api/auth/v1/introspect/"
SECRET = {"HTTP_X_SERVICE_SECRET": "dev-service-secret"}


def introspect(api, token, secret=True):
    return api.post(
        URL, {"token": token}, content_type="application/json", **(SECRET if secret else {})
    )


def result(response):
    return Introspection.from_payload(response.json())


def test_an_active_token_reports_the_users_current_roles(api, make_user):
    user = make_user(roles=("reader", "editor"))
    token = login(api).json()["access_token"]

    assert result(introspect(api, token)) == Introspection(True, str(user.id), ("editor", "reader"))


def test_a_demotion_shows_up_before_the_token_expires(api, make_user):
    user = make_user(roles=("reader", "editor"))
    token = login(api).json()["access_token"]
    user.roles.set(user.roles.filter(name="reader"))

    assert result(introspect(api, token)).roles == ("reader",)


def test_a_disabled_user_is_inactive_immediately(api, make_user):
    user = make_user()
    token = login(api).json()["access_token"]
    User.objects.filter(pk=user.pk).update(is_active=False)

    assert result(introspect(api, token)) == Introspection(False)


def test_a_deleted_user_is_inactive(api, make_user):
    user = make_user()
    token = login(api).json()["access_token"]
    user.delete()

    assert result(introspect(api, token)) == Introspection(False)


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "x" * 500])
def test_garbage_is_inactive_not_an_error(api, db, token):
    assert result(introspect(api, token)) == Introspection(False)


def test_a_token_signed_by_an_unknown_key_is_inactive(api, make_user):
    user = make_user()
    keys.active_key()
    forged = TestKey("forged").sign(issue_claims(str(user.id), [Role.EDITOR], AUDIENCE_APP, 600))

    assert result(introspect(api, forged)) == Introspection(False)


def test_a_token_for_an_unregistered_audience_is_inactive(api, make_user):
    user = make_user()
    key = keys.active_key()
    import jwt

    payload = encode_claims(issue_claims(str(user.id), [], "somebody-else", 600))
    token = jwt.encode(payload, key.private_pem, algorithm="EdDSA", headers={"kid": key.kid})

    assert result(introspect(api, token)) == Introspection(False)


def test_a_freshly_rotated_key_is_accepted_at_once(api, make_user):
    make_user()
    introspect(api, login(api).json()["access_token"])  # warms the verifier's key cache
    keys.create_key()

    assert result(introspect(api, login(api).json()["access_token"])).active


@pytest.mark.parametrize("secret", [False, True])
def test_the_service_secret_is_required(api, make_user, secret):
    make_user()
    token = login(api).json()["access_token"]

    response = introspect(api, token, secret=secret)

    assert response.status_code == (200 if secret else 401)


def test_a_wrong_service_secret_is_a_401(api, make_user):
    make_user()
    token = login(api).json()["access_token"]

    response = api.post(
        URL, {"token": token}, content_type="application/json", HTTP_X_SERVICE_SECRET="nope"
    )

    assert response.status_code == 401


def test_a_missing_token_field_is_a_400(api, db):
    assert api.post(URL, {}, content_type="application/json", **SECRET).status_code == 400
