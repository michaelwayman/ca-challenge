"""Checking a token: is it signed by the auth service, for this service, and not expired?

`TokenVerifier.verify()` does the checking. It gets the auth service's public keys from a
`JWKSClient`, which keeps them in memory so most requests make no network call.
"""

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

# Returns the auth service's JWKS document: {"keys": [{"kid": ..., ...}, ...]}.
FetchKeys = Callable[[], Mapping[str, Any]]


def http_fetch(url: str, timeout: float = 2.0) -> FetchKeys:
    """A FetchKeys that downloads the JWKS document from `url`. The timeout is short because
    the download can happen while a request is waiting."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"JWKS URL must be http(s): {url!r}")

    def fetch() -> Mapping[str, Any]:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.load(response)

    return fetch


class JWKSClient:
    """Keeps the auth service's public keys in memory, looked up by key id (`kid`).

    - Keys younger than `ttl` seconds are used as they are.
    - Otherwise (old keys, or a `kid` we have never seen, which is how a newly rotated key
      shows up) the keys are downloaded again, but at most once every `min_interval`
      seconds, so junk tokens or an outage can't turn every request into a download.
    - If a download fails, the keys we already have are still used.
    """

    def __init__(
        self,
        fetch: FetchKeys,
        *,
        ttl: float = 300.0,
        min_interval: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self._ttl = ttl
        self._min_interval = min_interval
        self._clock = clock
        self._lock = threading.Lock()  # requests run in several threads

        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_fetched_at: float | None = None  # when `_keys` was last downloaded
        self._last_refresh_at: float | None = None  # when we last tried, successful or not
        self._last_refresh_failed = False

    def key_for(self, kid: str) -> jwt.PyJWK:
        """The public key with id `kid`. Raises TokenError if the auth service doesn't have
        it, and KeysUnavailable if the keys can't be downloaded to find out."""
        with self._lock:
            now = self._clock()

            if kid in self._keys and self._keys_are_fresh(now):
                return self._keys[kid]

            if self._may_refresh(now):
                self._refresh(now)

            if kid in self._keys:
                return self._keys[kid]  # possibly an old copy, if the download just failed
            if self._last_refresh_failed:
                raise KeysUnavailable("signing keys could not be fetched")
            raise TokenError(f"unknown signing key: {kid}")

    def _keys_are_fresh(self, now: float) -> bool:
        return self._keys_fetched_at is not None and now - self._keys_fetched_at < self._ttl

    def _may_refresh(self, now: float) -> bool:
        return self._last_refresh_at is None or now - self._last_refresh_at >= self._min_interval

    def _refresh(self, now: float) -> None:
        self._last_refresh_at = now
        try:
            document = self._fetch()
            keys = {key["kid"]: jwt.PyJWK.from_dict(key) for key in document["keys"]}
        except Exception:  # noqa: BLE001  any failure: keep the keys we have
            self._last_refresh_failed = True
            return
        self._keys = keys
        self._keys_fetched_at = now
        self._last_refresh_failed = False


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
        self._leeway = leeway  # seconds of clock difference to tolerate
        # Only these algorithms are accepted; that is what stops `alg: none` tokens and
        # tokens signed with the public key as an HMAC secret.
        self._algorithms = list(algorithms)

    def verify(self, token: str) -> Claims:
        """The claims of a valid token. Raises TokenError for a bad token, and
        KeysUnavailable when the keys needed to decide can't be fetched."""
        key = self._keys.key_for(_key_id(token))
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


def _key_id(token: str) -> str:
    """The `kid` from the token's header: which of the auth service's keys signed it."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("malformed token") from exc
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenError("token has no key id")
    return kid
