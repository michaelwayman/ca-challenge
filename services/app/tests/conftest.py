import httpx
import pytest

from catalog import auth
from shared.auth import drf

from .fake_auth import FakeAuthService


@pytest.fixture
def auth_service(monkeypatch):
    """The auth service replaced by a fake: JWKS, introspection and sign-in."""
    service = FakeAuthService()
    drf.reset_verifier()
    monkeypatch.setattr(drf, "http_fetch", service.jwks_fetch)
    monkeypatch.setattr(auth, "_transport", httpx.MockTransport(service.handle))
    yield service
    drf.reset_verifier()
