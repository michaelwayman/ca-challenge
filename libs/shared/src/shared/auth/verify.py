import json
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

import jwt

from .claims import Claims, decode_claims
from .errors import KeysUnavailable, TokenError

Fetch = Callable[[], Mapping[str, Any]]


def http_fetch(url: str, timeout: float = 2.0) -> Fetch:
    """A fetcher for a JWKS URL. Short timeout: it runs on the request path."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"JWKS URL must be http(s): {url!r}")

    def fetch() -> Mapping[str, Any]:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.load(response)

    return fetch


class JWKSClient:
    """Caches the issuer's public keys by `kid`.

    - Keys are reused for `ttl` seconds, then refreshed.
    - An unknown `kid` triggers a refresh (that is how a rotated-in key is picked up).
    - Refresh attempts, successful or not, are at least `min_interval` apart, so a flood
      of bad kids or an outage cannot turn every request into a call to the issuer.
    - If a refresh fails, the cached keys keep being used: an outage at the issuer does
      not stop verification. With no keys cached at all, KeysUnavailable is raised.
    """

    def __init__(
        self,
        fetch: Fetch,
        *,
        ttl: float = 300.0,
        min_interval: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self._ttl = ttl
        self._min_interval = min_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None
        self._last_attempt_failed = False

    def key_for(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            now = self._clock()
            fresh = self._fetched_at is not None and now - self._fetched_at < self._ttl
            if kid in self._keys and fresh:
                return self._keys[kid]
            if self._last_attempt is None or now - self._last_attempt >= self._min_interval:
                self._refresh(now)
            if kid in self._keys:
                return self._keys[kid]
            if self._last_attempt_failed:
                raise KeysUnavailable("signing keys could not be fetched")
            raise TokenError(f"unknown signing key: {kid}")

    def _refresh(self, now: float) -> None:
        self._last_attempt = now
        try:
            document = self._fetch()
            keys = {k["kid"]: jwt.PyJWK.from_dict(k) for k in document["keys"]}
        except Exception:  # noqa: BLE001  any failure means "keep what we have"
            self._last_attempt_failed = True
            return
        self._keys = keys
        self._fetched_at = now
        self._last_attempt_failed = False


class TokenVerifier:
    def __init__(
        self,
        keys: JWKSClient,
        *,
        issuer: str,
        audience: str | Iterable[str],
        leeway: int = 10,
        algorithms: Iterable[str] = ("EdDSA",),
    ):
        self._keys = keys
        self._issuer = issuer
        self._audience = audience if isinstance(audience, str) else list(audience)
        self._leeway = leeway
        # An explicit allowlist is what stops `alg: none` and key-confusion tokens.
        self._algorithms = list(algorithms)

    def verify(self, token: str) -> Claims:
        """Return the claims of a valid token. Raises TokenError for a bad token and
        KeysUnavailable when the keys needed to decide cannot be obtained."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("malformed token") from exc
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenError("token has no key id")
        key = self._keys.key_for(kid)
        try:
            payload = jwt.decode(
                token,
                key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(str(exc)) from exc
        return decode_claims(payload)
