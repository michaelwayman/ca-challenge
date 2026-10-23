import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from shared.auth.claims import encode_claims, issue_claims

from . import keys
from .models import RefreshToken, User


def issue_access_token(user: User, audience: str) -> str:
    claims = issue_claims(str(user.id), user.role_names(), audience, settings.ACCESS_TOKEN_TTL)
    return keys.sign(encode_claims(claims))


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_refresh_token(user: User, audience: str) -> str:
    raw = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        user=user,
        token_hash=_hash(raw),
        audience=audience,
        expires_at=timezone.now() + timedelta(seconds=settings.REFRESH_TOKEN_TTL),
    )
    return raw


def token_pair(user: User, audience: str) -> dict:
    return {
        "access_token": issue_access_token(user, audience),
        "refresh_token": issue_refresh_token(user, audience),
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL,
    }


def redeem_refresh_token(raw: str) -> dict | None:
    """Exchange a refresh token for a new pair. The old one dies, so a stolen copy can
    be used at most once and only if the owner has not used it first. Returns None for
    an unknown, used, expired token or a disabled user."""
    with transaction.atomic():
        token = (
            RefreshToken.objects.select_for_update()
            .select_related("user")
            .filter(token_hash=_hash(raw))
            .first()
        )
        now = timezone.now()
        if (
            token is None
            or token.revoked_at is not None
            or token.expires_at <= now
            or not token.user.is_active
        ):
            return None
        token.revoked_at = now
        token.save(update_fields=["revoked_at"])
        return token_pair(token.user, token.audience)


def purge_refresh_tokens(now=None, *, dry_run: bool = False) -> int:
    """Delete refresh tokens past their expiry, used or not, and return how many.

    Each login and each refresh adds a row, and redeeming one only marks it revoked, so
    without this the table grows for ever. A revoked token is kept until it expires, so
    reuse detection can still recognise it if that is added.
    """
    expired = RefreshToken.objects.filter(expires_at__lte=now or timezone.now())
    count = expired.count()
    if not dry_run:
        expired.delete()
    return count
