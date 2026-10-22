"""Helpers for tests in any package that handles tokens: make a key pair, publish its
JWKS, sign a token. Not used at runtime."""

import base64
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .claims import Claims, encode_claims


class TestKey:
    __test__ = False  # not a pytest class

    def __init__(self, kid: str | None = None):
        self.kid = kid or uuid.uuid4().hex[:8]
        self.private = ed25519.Ed25519PrivateKey.generate()

    @property
    def jwk(self) -> dict[str, str]:
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "alg": "EdDSA",
            "use": "sig",
            "kid": self.kid,
            "x": x,
        }

    def sign(self, claims: Claims | dict[str, Any], **header: Any) -> str:
        payload = encode_claims(claims) if isinstance(claims, Claims) else claims
        return jwt.encode(
            payload, self.private, algorithm="EdDSA", headers={"kid": self.kid, **header}
        )


def jwks_document(*keys: TestKey) -> dict[str, Any]:
    return {"keys": [key.jwk for key in keys]}
