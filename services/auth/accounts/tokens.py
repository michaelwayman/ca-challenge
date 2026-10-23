"""Signing in, refreshing and checking tokens. The views in views.py only parse the request
and turn these results into responses.

- An access token is a signed JWT, valid for ACCESS_TOKEN_TTL. Services check it themselves
  with the public keys (keys.py).
- A refresh token is a random string, valid for REFRESH_TOKEN_TTL. Only its hash is stored,
  and it works once: using it returns a new pair and kills the old refresh token.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from shared.auth.claims import ISSUER, Introspection, encode_claims, issue_claims
from shared.auth.errors import KeysUnavailable, TokenError
from shared.auth.verify import JWKSClient, TokenVerifier

from . import keys
from .models import RefreshToken, User

# Checked when the username doesn't exist, so an unknown user takes as long as a wrong password.
_DUMMY_PASSWORD_HASH = make_password("not-a-real-password")


def check_credentials(username: str, password: str) -> User | None:
    """The user, if the username and password are right and the account is enabled.

    A missing user, a wrong password, a user without a usable password and a disabled user
    all return None in about the same time, so a caller can't tell them apart.
    """
    user = User.objects.filter(username=username).first()
    if user is None:
        check_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if user.check_password(password) and user.is_active:
        return user
    return None


def token_pair(user: User, audience: str) -> dict:
    """What a successful sign-in or refresh returns."""
    return {
        "access_token": _access_token(user, audience),
        "refresh_token": _new_refresh_token(user, audience),
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL,
    }


def redeem_refresh_token(raw: str) -> dict | None:
    """A new token pair for a refresh token, which is used up in the process.

    None if the token is unknown, already used, expired, or belongs to a disabled user. Using
    a token up means a stolen copy works at most once, and only if the owner hasn't used it.
    """
    with transaction.atomic():
        token = (
            RefreshToken.objects.select_for_update()  # two requests can't both redeem it
            .select_related("user")
            .filter(token_hash=_hash(raw))
            .first()
        )
        now = timezone.now()
        if token is None or not _is_usable(token, now):
            return None
        token.revoked_at = now
        token.save(update_fields=["revoked_at"])
        return token_pair(token.user, token.audience)


def introspect(raw_token: str) -> Introspection:
    """Is this access token still good, and what may its holder do right now?

    Answers from the database, not from the token: a disabled user or a role change shows up
    at once, rather than when the token expires.
    """
    inactive = Introspection(active=False)
    try:
        claims = _own_verifier().verify(raw_token)
    except (TokenError, KeysUnavailable):
        return inactive
    try:
        user = User.objects.filter(pk=claims.sub, is_active=True).first()
    except (ValidationError, ValueError):  # `sub` isn't a UUID
        return inactive
    if user is None:
        return inactive
    return Introspection(active=True, sub=str(user.id), roles=tuple(user.role_names()))


def purge_refresh_tokens(now=None, *, dry_run: bool = False) -> int:
    """Delete refresh tokens past their expiry, used or not, and return how many.

    Every sign-in and refresh adds a row, and using a token only marks it revoked, so
    without this the table grows for ever. A revoked token is kept until it expires, so
    reuse detection could still recognise it if it is added.
    """
    expired = RefreshToken.objects.filter(expires_at__lte=now or timezone.now())
    count = expired.count()
    if not dry_run:
        expired.delete()
    return count


def _access_token(user: User, audience: str) -> str:
    claims = issue_claims(str(user.id), user.role_names(), audience, settings.ACCESS_TOKEN_TTL)
    return keys.sign(encode_claims(claims))


def _new_refresh_token(user: User, audience: str) -> str:
    raw = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        user=user,
        token_hash=_hash(raw),
        audience=audience,
        expires_at=timezone.now() + timedelta(seconds=settings.REFRESH_TOKEN_TTL),
    )
    return raw


def _is_usable(token: RefreshToken, now) -> bool:
    return token.revoked_at is None and token.expires_at > now and token.user.is_active


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _own_verifier() -> TokenVerifier:
    """A verifier that reads this service's keys directly from the database (no HTTP), and
    re-reads them after 5 seconds, so a key that was just rotated in is accepted at once."""
    return TokenVerifier(
        JWKSClient(keys.jwks_document, ttl=5, min_interval=0),
        issuer=ISSUER,
        audience=sorted(settings.AUDIENCES),
    )
