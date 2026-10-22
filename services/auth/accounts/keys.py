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


def create_key() -> SigningKey:
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


def _jwk(key: SigningKey) -> dict[str, str]:
    private = serialization.load_pem_private_key(key.private_pem.encode(), password=None)
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "use": "sig", "kid": key.kid, "x": x}


def jwks_document() -> dict[str, Any]:
    active_key()  # make sure at least one key exists to publish
    keys = SigningKey.objects.filter(retired_at__isnull=True).order_by("created_at", "id")
    return {"keys": [_jwk(k) for k in keys]}


def sign(payload: dict[str, Any]) -> str:
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
