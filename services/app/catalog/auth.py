"""Client for the auth service's introspection endpoint, used by the write endpoint.

Lives here, not in the shared library: only this service calls it, and it changes with
the auth service's API. The library's `require_role(..., fresh=True)` reaches it through
settings.CA_AUTH["INTROSPECTOR"].
"""

import logging

import httpx
from django.conf import settings

from ca_authlib.claims import Introspection
from ca_authlib.errors import IntrospectionUnavailable, InvalidIntrospection

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
