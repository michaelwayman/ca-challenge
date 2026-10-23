"""What an access token says. The auth service writes tokens with this module and the
main app reads them with it, so the two can't disagree about the format.

Changing the token format (expand/contract):
1. Expand: add the new claim. The auth service writes both the old and the new one.
2. Move every reader to the new claim. Readers ignore claims they don't know.
3. Contract: stop writing the old claim once nothing reads it.
Never change what an existing claim means; add a claim with a new name instead.
"""

import time
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .errors import InvalidClaims, InvalidIntrospection

ISSUER = "brand-reviews-auth"
AUDIENCE_APP = "brand-reviews-app"


class Role(StrEnum):
    READER = "reader"
    EDITOR = "editor"


@dataclass(frozen=True)
class Claims:
    sub: str  # the user's id in the auth service
    roles: tuple[str, ...]
    iss: str  # who issued the token
    aud: str  # which service the token is for
    iat: int  # issued at (unix seconds)
    exp: int  # expires at (unix seconds)
    jti: str  # unique token id

    def has_role(self, role: str) -> bool:
        return str(role) in self.roles


def issue_claims(
    sub: str, roles: Iterable[str], audience: str, ttl_seconds: int, *, now: int | None = None
) -> Claims:
    """The claims for a new token, valid for `ttl_seconds` from now."""
    issued_at = int(time.time()) if now is None else now
    return Claims(
        sub=sub,
        roles=tuple(sorted(str(role) for role in roles)),
        iss=ISSUER,
        aud=audience,
        iat=issued_at,
        exp=issued_at + ttl_seconds,
        jti=uuid.uuid4().hex,
    )


def encode_claims(claims: Claims) -> dict[str, Any]:
    """The JWT payload for `claims`."""
    return {
        "iss": claims.iss,
        "aud": claims.aud,
        "sub": claims.sub,
        "iat": claims.iat,
        "exp": claims.exp,
        "jti": claims.jti,
        "roles": list(claims.roles),
    }


def decode_claims(payload: Mapping[str, Any]) -> Claims:
    """Read the claims from a payload whose signature has already been checked.

    Claims this code doesn't know are ignored, which is what lets a new claim be added
    before every reader understands it. A missing or wrongly typed claim is rejected.
    """
    try:
        sub, roles, jti = payload["sub"], payload["roles"], payload["jti"]
        iss, aud, iat, exp = payload["iss"], payload["aud"], payload["iat"], payload["exp"]
    except KeyError as missing:
        raise InvalidClaims(f"missing claim: {missing.args[0]}") from missing

    if not (isinstance(sub, str) and sub and isinstance(jti, str)):
        raise InvalidClaims("sub and jti must be non-empty strings")
    if not (isinstance(roles, list) and all(isinstance(role, str) for role in roles)):
        raise InvalidClaims("roles must be a list of strings")
    if not (isinstance(iss, str) and isinstance(aud, str)):
        raise InvalidClaims("iss and aud must be strings")
    if not (isinstance(iat, int) and isinstance(exp, int)):
        raise InvalidClaims("iat and exp must be integers")

    return Claims(sub=sub, roles=tuple(roles), iss=iss, aud=aud, iat=iat, exp=exp, jti=jti)


@dataclass(frozen=True)
class Introspection:
    """The auth service's answer to "is this token still good, and what may its holder do
    now?" (shaped after RFC 7662). The roles come from the auth database, not the token."""

    active: bool
    sub: str | None = None
    roles: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        if not self.active:
            return {"active": False}
        return {"active": True, "sub": self.sub, "roles": list(self.roles)}

    @classmethod
    def from_payload(cls, payload: Any) -> "Introspection":
        if not isinstance(payload, Mapping) or not isinstance(payload.get("active"), bool):
            raise InvalidIntrospection("introspection response has no boolean 'active'")
        if not payload["active"]:
            return cls(active=False)

        sub, roles = payload.get("sub"), payload.get("roles")
        if not isinstance(sub, str):
            raise InvalidIntrospection("introspection sub must be a string")
        if not (isinstance(roles, list) and all(isinstance(role, str) for role in roles)):
            raise InvalidIntrospection("introspection roles must be a list of strings")
        return cls(active=True, sub=sub, roles=tuple(roles))
