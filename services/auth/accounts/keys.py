"""The keys this service signs access tokens with.

A key's life:
1. Created by `rotate_signing_key` (or on first use). The newest unretired key signs.
2. Published at /.well-known/jwks.json while it isn't retired, so services can check the
   tokens it signed even after a newer key takes over.
3. Retired (`rotate_signing_key --retire-old`) once every token it signed has expired.
4. Deleted by `purge_tokens` a little later, taking its private key with it.
"""

import base64
import secrets
from datetime import timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from django.conf import settings
from django.utils import timezone

from .models import SigningKey

# How long a service may keep using a copy of the published keys (shared.auth.verify.JWKSClient).
JWKS_CACHE_SECONDS = 300


def create_key() -> SigningKey:
    """A new Ed25519 key pair. Being the newest, it signs from now on."""
    private = ed25519.Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return SigningKey.objects.create(kid=secrets.token_hex(6), private_pem=pem)


def active_key() -> SigningKey:
    """The newest unretired key, created on first use so a fresh install just works."""
    key = SigningKey.objects.filter(retired_at__isnull=True).order_by("-created_at", "-id").first()
    return key or create_key()


def _public_jwk(key: SigningKey) -> dict[str, str]:
    """The public half of `key`, in the JWK format services read."""
    private = serialization.load_pem_private_key(key.private_pem.encode(), password=None)
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "use": "sig", "kid": key.kid, "x": x}


def jwks_document() -> dict[str, Any]:
    """Every unretired public key: what /.well-known/jwks.json serves."""
    active_key()  # make sure there is at least one key to publish
    keys = SigningKey.objects.filter(retired_at__isnull=True).order_by("created_at", "id")
    return {"keys": [_public_jwk(key) for key in keys]}


def sign(payload: dict[str, Any]) -> str:
    """A JWT of `payload`, signed with the active key and naming it in the `kid` header."""
    key = active_key()
    return jwt.encode(payload, key.private_pem, algorithm="EdDSA", headers={"kid": key.kid})


def retire_old_keys(now=None) -> int:
    """Retire keys that stopped signing more than one access-token lifetime ago, so every
    token they signed has expired. A key stops signing when the next one is created."""
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=settings.ACCESS_TOKEN_TTL)
    keys = list(SigningKey.objects.filter(retired_at__isnull=True).order_by("created_at", "id"))
    retired = 0
    for key, successor in zip(keys, keys[1:], strict=False):
        if successor.created_at <= cutoff:
            key.retired_at = now
            key.save(update_fields=["retired_at"])
            retired += 1
    return retired


def purge_retired_keys(now=None, *, dry_run: bool = False) -> int:
    """Delete keys retired longer ago than one access-token lifetime plus the JWKS cache,
    and return how many. A retired key is no longer published, and every token it signed
    had expired before it was retired; the margin only covers a cached JWKS copy. Deleting
    the row also removes its private key from the database."""
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=settings.ACCESS_TOKEN_TTL + JWKS_CACHE_SECONDS)
    stale = SigningKey.objects.filter(retired_at__lte=cutoff)
    count = stale.count()
    if not dry_run:
        stale.delete()
    return count
