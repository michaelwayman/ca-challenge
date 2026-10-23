import hmac

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.auth.claims import AUDIENCE_APP, ISSUER, Introspection
from shared.auth.errors import KeysUnavailable, TokenError
from shared.auth.verify import JWKSClient, TokenVerifier

from . import keys, tokens
from .models import User

INVALID_CREDENTIALS = {"detail": "Invalid credentials."}
_DUMMY_HASH = make_password("not-a-real-password")


class PublicView(APIView):
    authentication_classes = []
    permission_classes = []


class TokenRequest(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=1024)
    audience = serializers.CharField(required=False, default=AUDIENCE_APP)


class TokenView(PublicView):
    def post(self, request):
        data = TokenRequest(data=request.data)
        data.is_valid(raise_exception=True)
        audience = data.validated_data["audience"]
        if audience not in settings.AUDIENCES:
            return Response({"audience": "Unknown audience."}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(username=data.validated_data["username"]).first()
        password = data.validated_data["password"]
        if user is None:
            check_password(password, _DUMMY_HASH)  # same cost as a real check
            return Response(INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)
        # Wrong password, unusable password and disabled user all look the same.
        if not (user.check_password(password) and user.is_active):
            return Response(INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)
        return Response(tokens.token_pair(user, audience))


class RefreshRequest(serializers.Serializer):
    refresh_token = serializers.CharField(max_length=256)


class RefreshView(PublicView):
    def post(self, request):
        data = RefreshRequest(data=request.data)
        data.is_valid(raise_exception=True)
        pair = tokens.redeem_refresh_token(data.validated_data["refresh_token"])
        if pair is None:
            return Response(
                {"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(pair)


def jwks(request):
    response = JsonResponse(keys.jwks_document())
    response["Cache-Control"] = "public, max-age=300"
    return response


def _verifier() -> TokenVerifier:
    # Reads the keys in-process (short cache, no refetch limit) so a key that was just
    # rotated in is accepted immediately.
    return TokenVerifier(
        JWKSClient(keys.jwks_document, ttl=5, min_interval=0),
        issuer=ISSUER,
        audience=sorted(settings.AUDIENCES),
    )


class IntrospectRequest(serializers.Serializer):
    token = serializers.CharField(max_length=8192)


class IntrospectView(PublicView):
    """For other services only (shared secret). Answers from the database, so a disabled
    user or a changed role is reflected at once, unlike the token's own claims."""

    def post(self, request):
        secret = request.headers.get("X-Service-Secret", "")
        if not hmac.compare_digest(secret.encode(), settings.SERVICE_SECRET.encode()):
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)
        data = IntrospectRequest(data=request.data)
        data.is_valid(raise_exception=True)
        inactive = Response(Introspection(active=False).to_payload())
        try:
            claims = _verifier().verify(data.validated_data["token"])
        except (TokenError, KeysUnavailable):
            return inactive
        try:
            user = User.objects.filter(pk=claims.sub, is_active=True).first()
        except (ValidationError, ValueError):
            return inactive
        if user is None:
            return inactive
        return Response(
            Introspection(
                active=True, sub=str(user.id), roles=tuple(user.role_names())
            ).to_payload()
        )
