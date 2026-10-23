import pytest

from shared.auth import claims as claims_module
from shared.auth.claims import (
    AUDIENCE_APP,
    Claims,
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

        assert (a.iat, a.exp, a.v) == (1000, 1600, 1)
        assert a.roles == ("editor", "reader")
        assert a.jti != b.jti

    def test_has_role(self):
        claims = issue_claims("u", [Role.READER], AUDIENCE_APP, 60)

        assert claims.has_role("reader")
        assert claims.has_role(Role.READER)
        assert not claims.has_role(Role.EDITOR)


class TestRoundTrip:
    def test_v1_round_trips(self):
        claims = issue_claims("u", [Role.EDITOR], AUDIENCE_APP, 600, now=1000)

        assert decode_claims(encode_claims(claims), accepted_versions=[1]) == claims

    def test_payload_carries_the_version(self):
        assert encode_claims(issue_claims("u", [], AUDIENCE_APP, 60))["v"] == 1


class TestVersionDispatch:
    def test_missing_version_is_rejected(self):
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60))
        del payload["v"]

        with pytest.raises(InvalidClaims, match="no version"):
            decode_claims(payload, accepted_versions=[1])

    @pytest.mark.parametrize("version", ["1", None, True, 1.0, 99])
    def test_unknown_or_malformed_version_is_rejected(self, version):
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60)) | {"v": version}

        with pytest.raises(InvalidClaims):
            decode_claims(payload, accepted_versions=[1])

    def test_a_known_version_the_service_does_not_accept_is_rejected(self, monkeypatch):
        monkeypatch.setitem(claims_module._DECODERS, 2, lambda p: p)
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60)) | {"v": 2}

        with pytest.raises(InvalidClaims, match="unsupported"):
            decode_claims(payload, accepted_versions=[1])

    def test_issuer_and_verifier_can_move_to_v2_independently(self, monkeypatch):
        """Auth can emit v2 while a service accepting [1, 2] keeps working with both."""
        monkeypatch.setitem(
            claims_module._ENCODERS,
            2,
            lambda c: {**claims_module._encode_v1(c), "v": 2, "extra": 1},
        )
        monkeypatch.setitem(
            claims_module._DECODERS,
            2,
            lambda p: Claims(
                p["sub"], tuple(p["roles"]), p["iss"], p["aud"], p["iat"], p["exp"], p["jti"], 2
            ),
        )
        v1 = issue_claims("u", [Role.READER], AUDIENCE_APP, 60)
        v2 = issue_claims("u", [Role.READER], AUDIENCE_APP, 60, version=2)

        assert decode_claims(encode_claims(v1), [1, 2]).v == 1
        assert decode_claims(encode_claims(v2), [1, 2]).v == 2
        with pytest.raises(InvalidClaims):
            decode_claims(encode_claims(v2), [1])  # a service that has not upgraded

    def test_encoding_an_unregistered_version_fails(self):
        with pytest.raises(InvalidClaims):
            encode_claims(issue_claims("u", [], AUDIENCE_APP, 60, version=7))


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
            decode_claims(payload, accepted_versions=[1])

    @pytest.mark.parametrize("missing", ["sub", "roles", "jti", "iss", "aud", "iat", "exp"])
    def test_every_claim_is_required(self, missing):
        payload = encode_claims(issue_claims("u", [], AUDIENCE_APP, 60))
        del payload[missing]

        with pytest.raises(InvalidClaims, match=missing):
            decode_claims(payload, accepted_versions=[1])


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
