"""A stand-in for the auth service: its signing keys and introspection endpoint."""

import json

import httpx

from shared.auth.claims import Introspection
from shared.auth.testing import TestKey, jwks_document

KEY = TestKey("k1")


class FakeAuthService:
    def __init__(self):
        self.jwks_down = False
        self.introspection_down = False
        self.introspection_status = 200
        self.introspection = Introspection(True, "user-1", ("editor", "reader"))
        self.introspection_calls = []

    def jwks_fetch(self, url):
        def fetch():
            if self.jwks_down:
                raise ConnectionError("down")
            return jwks_document(KEY)

        return fetch

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.introspection_calls.append((body["token"], request.headers.get("X-Service-Secret")))
        if self.introspection_down:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(self.introspection_status, json=self.introspection.to_payload())
