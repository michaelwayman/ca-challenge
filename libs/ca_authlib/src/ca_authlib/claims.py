"""The token contract: what an access token says, and how each version spells it.

Issuer and verifier both import this module, so they cannot drift apart. A token
carries a version in its `v` claim; encoding and decoding dispatch on it, which lets
auth issue a new version while services that only know the old one keep working
(and the reverse). To add a version, write an encoder and a decoder and register
them below.
"""

import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .errors import InvalidClaims, InvalidIntrospection

ISSUER = "brand-reviews-auth"
AUDIENCE_APP = "brand-reviews-app"
CURRENT_TOKEN_VERSION = 1


class Role(StrEnum):
    READER = "reader"
    EDITOR = "editor"


@dataclass(frozen=True)
class Claims:
    sub: str
    roles: tuple[str, ...]
    iss: str
    aud: str
    iat: int
    exp: int
    jti: str
    v: int

    def has_role(self, role: str) -> bool:
        return str(role) in self.roles


def issue_claims(
    sub: str,
    roles: Iterable[str],
    audience: str,
    ttl_seconds: int,
    *,
    version: int = CURRENT_TOKEN_VERSION,
    now: int | None = None,
) -> Claims:
    issued_at = int(time.time()) if now is None else now
    return Claims(
        sub=sub,
        roles=tuple(sorted(str(r) for r in roles)),
        iss=ISSUER,
        aud=audience,
        iat=issued_at,
        exp=issued_at + ttl_seconds,
        jti=uuid.uuid4().hex,
        v=version,
    )


def _encode_v1(claims: Claims) -> dict[str, Any]:
    return {
        "iss": claims.iss,
        "aud": claims.aud,
        "sub": claims.sub,
        "iat": claims.iat,
        "exp": claims.exp,
        "jti": claims.jti,
        "roles": list(claims.roles),
        "v": 1,
    }


def _decode_v1(payload: Mapping[str, Any]) -> Claims:
    try:
        sub, roles, jti = payload["sub"], payload["roles"], payload["jti"]
        iss, aud, iat, exp = payload["iss"], payload["aud"], payload["iat"], payload["exp"]
    except KeyError as exc:
        raise InvalidClaims(f"missing claim: {exc.args[0]}") from exc
    if not (isinstance(sub, str) and sub and isinstance(jti, str)):
        raise InvalidClaims("sub and jti must be non-empty strings")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise InvalidClaims("roles must be a list of strings")
    if not (isinstance(iss, str) and isinstance(aud, str)):
        raise InvalidClaims("iss and aud must be strings")
    if not (isinstance(iat, int) and isinstance(exp, int)):
        raise InvalidClaims("iat and exp must be integers")
    return Claims(sub, tuple(roles), iss, aud, iat, exp, jti, 1)


_ENCODERS: dict[int, Callable[[Claims], dict[str, Any]]] = {1: _encode_v1}
_DECODERS: dict[int, Callable[[Mapping[str, Any]], Claims]] = {1: _decode_v1}


def encode_claims(claims: Claims) -> dict[str, Any]:
    try:
        return _ENCODERS[claims.v](claims)
    except KeyError as exc:
        raise InvalidClaims(f"cannot encode token version {claims.v}") from exc


def decode_claims(payload: Mapping[str, Any], accepted_versions: Iterable[int]) -> Claims:
    """Parse a verified payload. A missing or unknown `v` is rejected, never guessed."""
    version = payload.get("v")
    if isinstance(version, bool) or not isinstance(version, int):
        raise InvalidClaims("token has no version")
    if version not in set(accepted_versions) or version not in _DECODERS:
        raise InvalidClaims(f"unsupported token version: {version}")
    return _DECODERS[version](payload)


@dataclass(frozen=True)
class Introspection:
    """The auth service's answer to "is this token still good, and what may it do now?"
    (shaped after RFC 7662). Roles come from the auth database, not from the token."""

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
        roles = payload.get("roles")
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise InvalidIntrospection("introspection roles must be a list of strings")
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise InvalidIntrospection("introspection sub must be a string")
        return cls(active=True, sub=sub, roles=tuple(roles))
