"""Django REST framework adapter: authenticate a bearer token, require a role.

Needs the `drf` extra. Configured through `settings.CA_AUTH`:

    CA_AUTH = {
        "JWKS_URL": "http://auth:8001/.well-known/jwks.json",
        "ISSUER": shared.auth.claims.ISSUER,
        "AUDIENCE": shared.auth.claims.AUDIENCE_APP,
        # Dotted path of a callable (token: str) -> Introspection. Only needed by
        # endpoints that use require_role(..., fresh=True). The client lives in the
        # service, because only that service calls the auth API.
        "INTROSPECTOR": "myapp.auth.introspect",
    }
"""

from dataclasses import dataclass
from functools import lru_cache

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
    id: str
    roles: tuple[str, ...]
    is_authenticated = True
    is_anonymous = False


@dataclass(frozen=True)
class VerifiedToken:
    claims: Claims
    raw: str


@lru_cache(maxsize=1)
def get_verifier() -> TokenVerifier:
    config = settings.CA_AUTH
    return TokenVerifier(
        JWKSClient(http_fetch(config["JWKS_URL"])),
        issuer=config["ISSUER"],
        audience=config["AUDIENCE"],
    )


class JWTAuthentication(BaseAuthentication):
    """`Authorization: Bearer <token>`. No header means anonymous (the view's
    permissions decide); a header that is present but bad is a 401."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Invalid Authorization header.")
        try:
            raw = parts[1].decode()
        except UnicodeDecodeError as exc:
            raise exceptions.AuthenticationFailed("Invalid Authorization header.") from exc
        try:
            claims = get_verifier().verify(raw)
        except KeysUnavailable as exc:
            raise AuthServiceUnavailable from exc
        except TokenError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        return AuthenticatedUser(id=claims.sub, roles=claims.roles), VerifiedToken(claims, raw)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


def require_role(role: str, *, fresh: bool = False) -> type[permissions.BasePermission]:
    """A permission class allowing only users holding `role`.

    A valid token's roles can be up to one token lifetime out of date. With
    `fresh=True` the auth service is asked for the user's current roles, so a revoked
    token or a demotion takes effect immediately. If it cannot be asked, the request
    fails with 503 rather than trusting the token's own roles.
    """

    class RequireRole(permissions.BasePermission):
        def has_permission(self, request, view):
            user = request.user
            if not getattr(user, "is_authenticated", False):
                return False  # DRF turns this into 401 because we set authenticate_header
            roles = user.roles
            if fresh:
                introspect = import_string(settings.CA_AUTH["INTROSPECTOR"])
                try:
                    result = introspect(request.auth.raw)
                except IntrospectionUnavailable as exc:
                    raise AuthServiceUnavailable from exc
                if not result.active:
                    raise exceptions.AuthenticationFailed("Token is no longer valid.")
                roles = result.roles
            return str(role) in roles

    RequireRole.__name__ = f"RequireRole_{role}"
    return RequireRole
