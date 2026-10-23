"""The auth service's HTTP API. Each view parses the request, calls tokens.py, and answers.

POST /api/auth/v1/token/        username + password -> token pair
POST /api/auth/v1/refresh/      refresh token       -> new token pair
POST /api/auth/v1/introspect/   access token        -> is it still good, current roles
GET  /.well-known/jwks.json     the public keys services check tokens with
"""

import hmac

from django.conf import settings
from django.http import JsonResponse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.auth.claims import AUDIENCE_APP

from . import keys, tokens


class PublicView(APIView):
    """No session or token needed to call these endpoints."""

    authentication_classes = []
    permission_classes = []


class TokenRequest(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=1024)
    audience = serializers.CharField(required=False, default=AUDIENCE_APP)


class TokenView(PublicView):
    def post(self, request):
        data = _validated(TokenRequest, request)
        if data["audience"] not in settings.AUDIENCES:
            return Response({"audience": "Unknown audience."}, status=status.HTTP_400_BAD_REQUEST)
        user = tokens.check_credentials(data["username"], data["password"])
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(tokens.token_pair(user, data["audience"]))


class RefreshRequest(serializers.Serializer):
    refresh_token = serializers.CharField(max_length=256)


class RefreshView(PublicView):
    def post(self, request):
        data = _validated(RefreshRequest, request)
        pair = tokens.redeem_refresh_token(data["refresh_token"])
        if pair is None:
            return Response(
                {"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(pair)


class IntrospectRequest(serializers.Serializer):
    token = serializers.CharField(max_length=8192)


class IntrospectView(PublicView):
    """For other services only: they must send the shared service secret."""

    def post(self, request):
        if not _has_service_secret(request):
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)
        data = _validated(IntrospectRequest, request)
        return Response(tokens.introspect(data["token"]).to_payload())


def jwks(request):
    response = JsonResponse(keys.jwks_document())
    response["Cache-Control"] = "public, max-age=300"
    return response


def _validated(serializer_class, request) -> dict:
    """The request body checked against `serializer_class`; a bad body is answered with 400."""
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _has_service_secret(request) -> bool:
    secret = request.headers.get("X-Service-Secret", "")
    return hmac.compare_digest(secret.encode(), settings.SERVICE_SECRET.encode())
