"""Django REST framework support: read a bearer token, and require a role.

Needs the `drf` extra. Configured in the service's settings:

    CA_AUTH = {
        "JWKS_URL": "http://auth:8001/.well-known/jwks.json",
        "ISSUER": shared.auth.claims.ISSUER,
        "AUDIENCE": shared.auth.claims.AUDIENCE_APP,
        # Only for RequireRole with fresh = True: dotted path to a function
        # (token: str) -> Introspection that asks the auth service about the token.
        "INTROSPECTOR": "myapp.auth.introspect",
    }

Protecting a view:

    class EditorOnly(RequireRole):
        role = Role.EDITOR

    class EditBrand(APIView):
        authentication_classes = [JWTAuthentication]
        permission_classes = [EditorOnly]
"""

from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework import exceptions, permissions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .claims import Claims
from .errors import IntrospectionUnavailable, KeysUnavailable, TokenError
from .verify import JWKSClient, TokenVerifier, http_fetch


class AuthServiceUnavailable(exceptions.APIException):
    status_code = 503
    default_detail = "Authentication service unavailable."
    default_code = "auth_unavailable"


@dataclass(frozen=True)
class AuthenticatedUser:
    """`request.user` for a request with a valid token."""

    id: str
    roles: tuple[str, ...]
    is_authenticated = True
    is_anonymous = False


@dataclass(frozen=True)
class VerifiedToken:
    """`request.auth` for a request with a valid token."""

    claims: Claims
    raw: str


_verifier: TokenVerifier | None = None


def get_verifier() -> TokenVerifier:
    """The verifier this process uses for every request.

    There is one per process because it holds the downloaded public keys: a new verifier per
    request would download them every time. It is built on first use because Django's
    settings aren't loaded yet when this module is imported.
    """
    global _verifier
    if _verifier is None:
        config = settings.CA_AUTH
        _verifier = TokenVerifier(
            JWKSClient(http_fetch(config["JWKS_URL"])),
            issuer=config["ISSUER"],
            audience=config["AUDIENCE"],
        )
    return _verifier


def reset_verifier() -> None:
    """Forget the verifier, so the next request builds a new one (tests, settings changes)."""
    global _verifier
    _verifier = None


class JWTAuthentication(BaseAuthentication):
    """Reads `Authorization: Bearer <token>`.

    No header: the request is anonymous, and the view's permissions decide. A header that is
    present but invalid: 401. The auth service's keys can't be fetched: 503.
    """

    def authenticate(self, request):
        raw = _bearer_token(request)
        if raw is None:
            return None
        try:
            claims = get_verifier().verify(raw)
        except KeysUnavailable as exc:
            raise AuthServiceUnavailable from exc
        except TokenError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        return AuthenticatedUser(id=claims.sub, roles=claims.roles), VerifiedToken(claims, raw)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'  # makes DRF answer 401, not 403, when there's no token


def _bearer_token(request) -> str | None:
    """The token from `Authorization: Bearer <token>`, or None if there is no bearer header."""
    parts = get_authorization_header(request).split()
    if not parts or parts[0].lower() != b"bearer":
        return None
    if len(parts) != 2:
        raise exceptions.AuthenticationFailed("Invalid Authorization header.")
    try:
        return parts[1].decode()
    except UnicodeDecodeError as exc:
        raise exceptions.AuthenticationFailed("Invalid Authorization header.") from exc


class RequireRole(permissions.BasePermission):
    """Allows only users holding `role`. Subclass it and set the attributes:

        class EditorWithFreshRoles(RequireRole):
            role = Role.EDITOR
            fresh = True

    The roles in a token can be up to one token lifetime out of date. With `fresh = True` the
    auth service is asked for the user's current roles, so a demotion or a disabled user takes
    effect at once; if it can't be asked, the request fails with 503 rather than trusting the
    token.
    """

    role: str = ""
    fresh: bool = False

    def has_permission(self, request, view):
        if not getattr(request.user, "is_authenticated", False):
            return False
        return str(self.role) in self._current_roles(request)

    def _current_roles(self, request) -> tuple[str, ...]:
        if not self.fresh:
            return request.user.roles
        introspect = import_string(settings.CA_AUTH["INTROSPECTOR"])
        try:
            answer = introspect(request.auth.raw)
        except IntrospectionUnavailable as exc:
            raise AuthServiceUnavailable from exc
        if not answer.active:
            raise exceptions.AuthenticationFailed("Token is no longer valid.")
        return answer.roles
