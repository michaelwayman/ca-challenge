import time

import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from shared.auth import drf
from shared.auth.claims import AUDIENCE_APP, ISSUER, Introspection, Role, issue_claims
from shared.auth.drf import JWTAuthentication, RequireRole
from shared.auth.errors import IntrospectionUnavailable
from shared.auth.testing import TestKey, jwks_document

factory = APIRequestFactory()


@pytest.fixture
def key():
    return TestKey("k1")


@pytest.fixture
def auth_settings(settings):
    settings.CA_AUTH = {
        "JWKS_URL": "http://auth.test/.well-known/jwks.json",
        "ISSUER": ISSUER,
        "AUDIENCE": AUDIENCE_APP,
        "INTROSPECTOR": "test_drf.fake_introspect",
    }
    return settings


@pytest.fixture(autouse=True)
def fresh_verifier():
    drf.reset_verifier()
    yield
    drf.reset_verifier()


@pytest.fixture
def serve_jwks(monkeypatch, key):
    state = {"down": False}

    def fake_http_fetch(url):
        def fetch():
            if state["down"]:
                raise ConnectionError("down")
            return jwks_document(key)

        return fetch

    monkeypatch.setattr(drf, "http_fetch", fake_http_fetch)
    return state


introspection = {"result": Introspection(True, "u1", ("editor", "reader")), "error": None}


def fake_introspect(token):
    if introspection["error"]:
        raise introspection["error"]
    return introspection["result"]


@pytest.fixture(autouse=True)
def reset_introspection():
    introspection.update(result=Introspection(True, "u1", ("editor", "reader")), error=None)


def token(key, roles=(Role.EDITOR,), **kwargs):
    return key.sign(issue_claims("u1", roles, AUDIENCE_APP, 600, now=int(time.time()), **kwargs))


def call(view_class, bearer=None, header=None):
    headers = {}
    if bearer is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {bearer}"
    if header is not None:
        headers["HTTP_AUTHORIZATION"] = header
    return view_class.as_view()(factory.get("/", **headers))


class WhoAmI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []

    def get(self, request):
        user = request.user
        return Response({"id": getattr(user, "id", None), "roles": getattr(user, "roles", None)})


class IsEditor(RequireRole):
    role = Role.EDITOR


class IsEditorNow(RequireRole):
    role = Role.EDITOR
    fresh = True


class EditorOnly(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsEditor]

    def get(self, request):
        return Response({"ok": True})


class EditorOnlyFresh(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsEditorNow]

    def get(self, request):
        return Response({"ok": True})


pytestmark = pytest.mark.usefixtures("auth_settings", "serve_jwks")


class TestAuthentication:
    def test_no_header_is_anonymous(self):
        response = call(WhoAmI)

        assert response.status_code == 200
        assert response.data == {"id": None, "roles": None}

    def test_a_valid_token_authenticates(self, key):
        response = call(WhoAmI, token(key, [Role.READER, Role.EDITOR]))

        assert response.data == {"id": "u1", "roles": ("editor", "reader")}

    @pytest.mark.parametrize("header", ["Basic abc", "Token abc"])
    def test_other_schemes_are_left_alone(self, header):
        assert call(WhoAmI, header=header).status_code == 200

    @pytest.mark.parametrize("header", ["Bearer", "Bearer a b"])
    def test_a_malformed_bearer_header_is_a_401(self, header):
        response = call(WhoAmI, header=header)

        assert response.status_code == 401

    def test_a_bad_token_is_a_401_even_on_a_public_view(self):
        response = call(WhoAmI, "garbage")

        assert response.status_code == 401
        assert response["WWW-Authenticate"] == 'Bearer realm="api"'

    def test_an_expired_token_is_a_401(self, key):
        stale = key.sign(issue_claims("u1", [], AUDIENCE_APP, -3600, now=int(time.time()) - 7200))

        assert call(WhoAmI, stale).status_code == 401

    def test_a_token_for_another_audience_is_a_401(self, key):
        other = key.sign(issue_claims("u1", [], "other-service", 600))

        assert call(WhoAmI, other).status_code == 401

    def test_keys_unavailable_is_a_503_not_a_401(self, key, serve_jwks):
        serve_jwks["down"] = True

        assert call(WhoAmI, token(key)).status_code == 503


class TestRequireRole:
    def test_anonymous_gets_401(self):
        response = call(EditorOnly)

        assert response.status_code == 401

    def test_a_reader_gets_403(self, key):
        assert call(EditorOnly, token(key, [Role.READER])).status_code == 403

    def test_an_editor_is_allowed(self, key):
        assert call(EditorOnly, token(key, [Role.EDITOR])).status_code == 200

    def test_a_subclass_without_a_role_allows_no_one(self, key):
        class NoRole(RequireRole):
            pass

        class Guarded(APIView):
            authentication_classes = [JWTAuthentication]
            permission_classes = [NoRole]

            def get(self, request):
                return Response({"ok": True})

        assert call(Guarded, token(key, [Role.EDITOR, Role.READER])).status_code == 403


class TestFreshRoles:
    def test_uses_the_introspected_roles(self, key):
        assert call(EditorOnlyFresh, token(key, [Role.EDITOR])).status_code == 200

    def test_a_demotion_wins_over_the_token(self, key):
        introspection["result"] = Introspection(True, "u1", ("reader",))

        # The token still says editor, but auth says otherwise.
        assert call(EditorOnlyFresh, token(key, [Role.EDITOR])).status_code == 403

    def test_introspected_roles_win_in_both_directions(self, key):
        introspection["result"] = Introspection(True, "u1", ("editor",))

        assert call(EditorOnlyFresh, token(key, [Role.READER])).status_code == 200

    def test_an_inactive_token_is_a_401(self, key):
        introspection["result"] = Introspection(False)

        assert call(EditorOnlyFresh, token(key)).status_code == 401

    def test_an_unreachable_auth_service_fails_closed_with_503(self, key):
        introspection["error"] = IntrospectionUnavailable("down")

        # Even though the token itself says editor.
        assert call(EditorOnlyFresh, token(key, [Role.EDITOR])).status_code == 503

    def test_anonymous_never_reaches_introspection(self):
        introspection["error"] = IntrospectionUnavailable("would be a 503")

        assert call(EditorOnlyFresh).status_code == 401
