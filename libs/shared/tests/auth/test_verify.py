import base64
import json
import time

import jwt
import pytest

from shared.auth.claims import AUDIENCE_APP, ISSUER, Role, encode_claims, issue_claims
from shared.auth.errors import InvalidClaims, KeysUnavailable, TokenError
from shared.auth.testing import TestKey, jwks_document
from shared.auth.verify import JWKSClient, TokenVerifier, http_fetch


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Issuer:
    """A fake auth service: serves a JWKS and counts the requests."""

    def __init__(self, *keys):
        self.keys = list(keys)
        self.calls = 0
        self.down = False

    def fetch(self):
        self.calls += 1
        if self.down:
            raise ConnectionError("auth is down")
        return jwks_document(*self.keys)


@pytest.fixture
def key():
    return TestKey("k1")


@pytest.fixture
def issuer(key):
    return Issuer(key)


@pytest.fixture
def clock():
    return Clock()


def make_verifier(issuer, clock, **kwargs):
    client = JWKSClient(issuer.fetch, ttl=300, min_interval=30, clock=clock)
    return TokenVerifier(client, issuer=ISSUER, audience=AUDIENCE_APP, **kwargs)


def claims(**kwargs):
    return issue_claims(
        "user-1",
        kwargs.pop("roles", [Role.EDITOR]),
        kwargs.pop("aud", AUDIENCE_APP),
        kwargs.pop("ttl", 600),
        now=kwargs.pop("now", int(time.time())),
        **kwargs,
    )


class TestValidTokens:
    def test_returns_the_claims(self, key, issuer, clock):
        token = key.sign(claims(roles=[Role.EDITOR, Role.READER]))

        result = make_verifier(issuer, clock).verify(token)

        assert result.sub == "user-1"
        assert result.roles == ("editor", "reader")
        assert result.aud == AUDIENCE_APP
        assert result.v == 1


class TestRejectedTokens:
    @pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "a.b"])
    def test_malformed(self, issuer, clock, token):
        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(token)

    def test_expired(self, key, issuer, clock):
        token = key.sign(claims(ttl=-60, now=1_000_000))

        with pytest.raises(TokenError, match="expired"):
            make_verifier(issuer, clock, leeway=0).verify(token)

    def test_wrong_audience(self, key, issuer, clock):
        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(key.sign(claims(aud="some-other-service")))

    def test_wrong_issuer(self, key, issuer, clock):
        payload = encode_claims(claims()) | {"iss": "evil"}

        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(key.sign(payload))

    def test_signed_by_a_different_key_with_a_known_kid(self, issuer, clock):
        forger = TestKey("k1")  # same kid, different key material

        with pytest.raises(TokenError, match="Signature"):
            make_verifier(issuer, clock).verify(forger.sign(claims()))

    def test_tampered_payload(self, key, issuer, clock):
        header, payload, signature = key.sign(claims(roles=[Role.READER])).split(".")
        forged = json.dumps(encode_claims(claims(roles=[Role.EDITOR]))).encode()
        forged_payload = base64.urlsafe_b64encode(forged).rstrip(b"=").decode()

        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(f"{header}.{forged_payload}.{signature}")

    def test_alg_none_is_rejected(self, issuer, clock):
        token = jwt.encode(encode_claims(claims()), None, algorithm="none", headers={"kid": "k1"})

        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(token)

    def test_hs256_signed_with_the_public_key_is_rejected(self, key, issuer, clock):
        # The classic key-confusion attack: sign with HMAC using the public key as the secret.
        token = jwt.encode(
            encode_claims(claims()), key.jwk["x"], algorithm="HS256", headers={"kid": "k1"}
        )

        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(token)

    def test_no_kid(self, key, issuer, clock):
        token = jwt.encode(encode_claims(claims()), key.private, algorithm="EdDSA")

        with pytest.raises(TokenError, match="key id"):
            make_verifier(issuer, clock).verify(token)

    def test_missing_required_claim(self, key, issuer, clock):
        payload = encode_claims(claims())
        del payload["sub"]

        with pytest.raises(TokenError):
            make_verifier(issuer, clock).verify(key.sign(payload))

    def test_missing_version_claim(self, key, issuer, clock):
        payload = encode_claims(claims())
        del payload["v"]

        with pytest.raises(InvalidClaims):
            make_verifier(issuer, clock).verify(key.sign(payload))

    def test_unaccepted_version(self, key, issuer, clock):
        payload = encode_claims(claims()) | {"v": 2}

        with pytest.raises(InvalidClaims):
            make_verifier(issuer, clock, accepted_versions=[1]).verify(key.sign(payload))


class TestKeyCaching:
    def test_keys_are_fetched_once_and_reused(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)

        for _ in range(5):
            verifier.verify(key.sign(claims()))

        assert issuer.calls == 1

    def test_keys_are_refreshed_after_the_ttl(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        verifier.verify(key.sign(claims()))

        clock.advance(301)
        verifier.verify(key.sign(claims()))

        assert issuer.calls == 2


class TestKeyRotation:
    def test_a_newly_published_key_is_picked_up_on_an_unknown_kid(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        verifier.verify(key.sign(claims()))
        new_key = TestKey("k2")
        issuer.keys.append(new_key)
        clock.advance(31)  # past the refetch rate limit, well inside the TTL

        assert verifier.verify(new_key.sign(claims())).sub == "user-1"
        assert issuer.calls == 2

    def test_old_tokens_keep_working_while_the_old_key_is_published(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        old_token = key.sign(claims())
        new_key = TestKey("k2")
        issuer.keys.append(new_key)

        assert verifier.verify(new_key.sign(claims())).sub == "user-1"
        assert verifier.verify(old_token).sub == "user-1"

    def test_unknown_kids_cannot_make_every_request_hit_the_issuer(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        verifier.verify(key.sign(claims()))
        attacker = TestKey("nope")

        for _ in range(20):
            with pytest.raises(TokenError, match="unknown signing key"):
                verifier.verify(attacker.sign(claims()))

        assert issuer.calls == 1  # the first fetch only; the flood was rate limited

    def test_a_retired_key_stops_verifying_after_the_next_refresh(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        token = key.sign(claims())
        verifier.verify(token)
        issuer.keys = [TestKey("k2")]
        clock.advance(301)

        with pytest.raises(TokenError, match="unknown signing key"):
            verifier.verify(token)


class TestIssuerOutage:
    def test_cached_keys_keep_verifying_through_an_outage(self, key, issuer, clock):
        verifier = make_verifier(issuer, clock)
        verifier.verify(key.sign(claims()))
        issuer.down = True
        clock.advance(600)  # the cache is stale and the refresh fails

        assert verifier.verify(key.sign(claims())).sub == "user-1"

    def test_with_no_keys_cached_an_outage_is_keys_unavailable_not_a_bad_token(
        self, key, issuer, clock
    ):
        issuer.down = True

        with pytest.raises(KeysUnavailable):
            make_verifier(issuer, clock).verify(key.sign(claims()))

    def test_an_outage_does_not_turn_every_request_into_a_fetch(self, key, issuer, clock):
        issuer.down = True
        verifier = make_verifier(issuer, clock)

        for _ in range(10):
            with pytest.raises(KeysUnavailable):
                verifier.verify(key.sign(claims()))

        assert issuer.calls == 1

    def test_recovers_once_the_issuer_is_back(self, key, issuer, clock):
        issuer.down = True
        verifier = make_verifier(issuer, clock)
        with pytest.raises(KeysUnavailable):
            verifier.verify(key.sign(claims()))

        issuer.down = False
        clock.advance(31)

        assert verifier.verify(key.sign(claims())).sub == "user-1"

    def test_a_malformed_jwks_counts_as_unavailable(self, key, clock):
        bad = Issuer()
        bad.fetch = lambda: {"nope": []}

        with pytest.raises(KeysUnavailable):
            make_verifier(bad, clock).verify(key.sign(claims()))


class TestHttpFetch:
    def test_rejects_non_http_urls(self):
        with pytest.raises(ValueError):
            http_fetch("file:///etc/passwd")
