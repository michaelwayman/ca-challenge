"""Client for the auth service: introspection (writes) and sign-in (the admin site).

Lives here, not in the shared library: only this service calls it, and it changes with
the auth service's API. The library's `require_role(..., fresh=True)` reaches it through
settings.CA_AUTH["INTROSPECTOR"].
"""

import logging

import httpx
from django.conf import settings

from ca_authlib.claims import Claims, Introspection
from ca_authlib.drf import get_verifier
from ca_authlib.errors import (
    IntrospectionUnavailable,
    InvalidIntrospection,
    KeysUnavailable,
    TokenError,
)

logger = logging.getLogger(__name__)

# Tests point this at httpx.MockTransport.
_transport: httpx.BaseTransport | None = None


def introspect(token: str) -> Introspection:
    """Ask the auth service whether `token` is still good and what its holder may do now.

    Any failure to get a clear answer (timeout, 5xx, a rejected service secret, a
    response in the wrong shape) is IntrospectionUnavailable, never "inactive": an
    outage must not look like a revocation, and must not look like permission either.
    """
    try:
        with httpx.Client(timeout=settings.AUTH_TIMEOUT_SECONDS, transport=_transport) as client:
            response = client.post(
                settings.AUTH_INTROSPECT_URL,
                json={"token": token},
                headers={"X-Service-Secret": settings.AUTH_SERVICE_SECRET},
            )
    except httpx.HTTPError as exc:
        logger.warning("introspection request failed: %s", exc)
        raise IntrospectionUnavailable(str(exc)) from exc
    if response.status_code != 200:
        logger.warning("introspection returned HTTP %s", response.status_code)
        raise IntrospectionUnavailable(f"auth service answered {response.status_code}")
    try:
        return Introspection.from_payload(response.json())
    except (ValueError, InvalidIntrospection) as exc:
        raise IntrospectionUnavailable("unreadable introspection response") from exc


def login(username: str, password: str) -> Claims | None:
    """Sign a person in through the auth service and return their verified token claims.

    None for any failure: wrong credentials, the auth service down or answering oddly, or a
    token that does not verify. The admin login treats every one of them as "not signed in".
    """
    try:
        with httpx.Client(timeout=settings.AUTH_TIMEOUT_SECONDS, transport=_transport) as client:
            response = client.post(
                settings.AUTH_TOKEN_URL, json={"username": username, "password": password}
            )
    except httpx.HTTPError as exc:
        logger.warning("admin sign-in: the auth service is unreachable: %s", exc)
        return None
    if response.status_code != 200:
        if response.status_code >= 500:
            logger.warning("admin sign-in: the auth service answered HTTP %s", response.status_code)
        return None
    try:
        return get_verifier().verify(response.json()["access_token"])
    except (ValueError, KeyError, TypeError, TokenError, KeysUnavailable) as exc:
        logger.warning("admin sign-in: unusable token response: %s", exc)
        return None
