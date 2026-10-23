import pytest
from django.test import Client

from accounts.models import Role, User
from shared.auth.claims import AUDIENCE_APP, ISSUER
from shared.auth.verify import JWKSClient, TokenVerifier

PASSWORD = "correct horse battery staple"  # noqa: S105


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """PBKDF2 is deliberately slow; tests do not need that (one test overrides this)."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def api():
    return Client()


@pytest.fixture
def make_user(db):
    def make(username="sarah", roles=("reader",), password=PASSWORD, **kwargs):
        user = User.objects.create_user(username, password=password, **kwargs)
        user.roles.set(Role.objects.filter(name__in=roles))
        return user

    return make


@pytest.fixture
def verifier(api):
    """A verifier that reads the service's published JWKS, like the main app does."""

    def fetch():
        return api.get("/.well-known/jwks.json").json()

    return TokenVerifier(
        JWKSClient(fetch, ttl=0, min_interval=0), issuer=ISSUER, audience=AUDIENCE_APP
    )


def post(api, path, **body):
    return api.post(path, body, content_type="application/json")


def login(api, username="sarah", password=PASSWORD, **extra):
    return post(api, "/api/auth/v1/token/", username=username, password=password, **extra)
