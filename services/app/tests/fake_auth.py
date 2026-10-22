"""A stand-in for the auth service: its signing keys, introspection and token endpoints."""

import json
import time

import httpx

from ca_authlib.claims import AUDIENCE_APP, Introspection, issue_claims
from ca_authlib.testing import TestKey, jwks_document

KEY = TestKey("k1")


class FakeAuthService:
    def __init__(self):
        self.jwks_down = False
        self.introspection_down = False
        self.introspection_status = 200
        self.introspection = Introspection(True, "user-1", ("editor", "reader"))
        self.introspection_calls = []
        self.token_down = False
        self.token_audience = AUDIENCE_APP
        self.token_calls = []
        self.accounts = {}  # username -> {"password", "sub", "roles"}

    def add_account(self, username, password, roles, sub=None):
        sub = sub or f"00000000-0000-4000-8000-{len(self.accounts) + 1:012d}"
        self.accounts[username] = {"password": password, "sub": sub, "roles": roles}
        return sub

    def jwks_fetch(self, url):
        def fetch():
            if self.jwks_down:
                raise ConnectionError("down")
            return jwks_document(KEY)

        return fetch

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/token/"):
            return self._token(request, body)
        self.introspection_calls.append((body["token"], request.headers.get("X-Service-Secret")))
        if self.introspection_down:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(self.introspection_status, json=self.introspection.to_payload())

    def _token(self, request, body):
        self.token_calls.append((body["username"], body["password"]))
        if self.token_down:
            raise httpx.ConnectError("refused", request=request)
        account = self.accounts.get(body["username"])
        if account is None or account["password"] != body["password"]:
            return httpx.Response(401, json={"detail": "Invalid credentials."})
        claims = issue_claims(
            account["sub"], account["roles"], self.token_audience, 600, now=int(time.time())
        )
        return httpx.Response(
            200, json={"access_token": KEY.sign(claims), "token_type": "Bearer", "expires_in": 600}
        )
