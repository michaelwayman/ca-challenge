import pytest

from shared.auth.claims import (
    AUDIENCE_APP,
    Introspection,
    Role,
    decode_claims,
    encode_claims,
    issue_claims,
)
from shared.auth.errors import InvalidClaims, InvalidIntrospection


class TestIssue:
    def test_builds_claims_with_ttl_sorted_roles_and_a_unique_jti(self):
        a = issue_claims("u", ["reader", "editor"], AUDIENCE_APP, 600, now=1000)
        b = issue_claims("u", ["reader", "editor"], AUDIENCE_APP, 600, now=1000)

        assert (a.iat, a.exp) == (1000, 1600)
        assert a.roles == ("editor", "reader")
        assert a.jti != b.jti

    def test_has_role(self):
        claims = issue_claims("u", [Role.READER], AUDIENCE_APP, 60)

        assert claims.has_role("reader")
        assert claims.has_role(Role.READER)
        assert not claims.has_role(Role.EDITOR)


class TestRoundTrip:
    def test_round_trips(self):
        claims = issue_claims("u", [Role.EDITOR], AUDIENCE_APP, 600, now=1000)

        assert decode_claims(encode_claims(claims)) == claims

    def test_claims_it_does_not_know_are_ignored(self):
        """Expand/contract relies on this: a new claim can be added before readers know it."""
        claims = issue_claims("u", [Role.READER], AUDIENCE_APP, 60)
        payload = encode_claims(claims) | {"permissions": ["brand:edit"], "v": 1}

        assert decode_claims(payload) == claims


class TestDecodeValidation:
    @pytest.mark.parametrize(
        "change",
        [
            {"roles": "editor"},
            {"roles": [1]},
            {"sub": ""},
            {"sub": 5},
            {"jti": None},
            {"aud": ["a", "b"]},
            {"exp": "soon"},
        ],
    )
    def test_malformed_claims_are_rejected(self, change):
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60)) | change

        with pytest.raises(InvalidClaims):
            decode_claims(payload)

    @pytest.mark.parametrize("missing", ["sub", "roles", "jti", "iss", "aud", "iat", "exp"])
    def test_every_claim_is_required(self, missing):
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60))
        del payload[missing]

        with pytest.raises(InvalidClaims, match=missing):
            decode_claims(payload)


class TestIntrospection:
    def test_active_round_trips(self):
        original = Introspection(active=True, sub="u", roles=("editor", "reader"))

        assert Introspection.from_payload(original.to_payload()) == original

    def test_inactive_carries_nothing_else(self):
        assert Introspection(active=False).to_payload() == {"active": False}
        assert Introspection.from_payload({"active": False, "roles": ["editor"]}) == Introspection(
            False
        )

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            [],
            {},
            {"active": "yes"},
            {"active": True},
            {"active": True, "roles": "x", "sub": "u"},
            {"active": True, "roles": [], "sub": 3},
        ],
    )
    def test_a_malformed_response_is_rejected(self, payload):
        with pytest.raises(InvalidIntrospection):
            Introspection.from_payload(payload)
