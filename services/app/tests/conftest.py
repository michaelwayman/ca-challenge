import httpx
import pytest

from ca_authlib import drf
from catalog import auth

from .fake_auth import FakeAuthService


@pytest.fixture
def auth_service(monkeypatch):
    """The auth service replaced by a fake: JWKS, introspection and sign-in."""
    service = FakeAuthService()
    drf.get_verifier.cache_clear()
    monkeypatch.setattr(drf, "http_fetch", service.jwks_fetch)
    monkeypatch.setattr(auth, "_transport", httpx.MockTransport(service.handle))
    yield service
    drf.get_verifier.cache_clear()
