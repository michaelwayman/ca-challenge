import logging

from django.db.models import F, Prefetch, Window
from django.db.models.functions import RowNumber
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Brand, Review
from shared.auth.claims import Role
from shared.auth.drf import JWTAuthentication, RequireRole

from .filters import filter_by_industry, order_brands
from .pagination import BrandPagination
from .serializers import BrandDetailSerializer, BrandListSerializer, BrandUpdateSerializer

logger = logging.getLogger(__name__)


def top_review_prefetch() -> Prefetch:
    """One query for the whole page: rank each brand's reviews and keep rank 1.

    "Top" is the highest rating, then the most recent, then the highest id.
    """
    ranked = Review.objects.annotate(
        rank=Window(
            RowNumber(),
            partition_by=F("brand"),
            order_by=[F("rating").desc(), F("published_at").desc(), F("id").desc()],
        )
    )
    return Prefetch(
        "reviews",
        queryset=ranked.filter(rank=1).select_related("reviewer"),
        to_attr="top_reviews",
    )


class BrandListView(ListAPIView):
    """Public, paginated brand listing: ?industry=<slug>&ordering=<field>&page=<n>."""

    serializer_class = BrandListSerializer
    pagination_class = BrandPagination

    def get_queryset(self):
        queryset = (
            Brand.objects.with_stats()
            .defer("seo")  # large and unused by the listing
            .prefetch_related("industries", top_review_prefetch())
        )
        queryset = filter_by_industry(queryset, self.request.query_params.getlist("industry"))
        return order_brands(queryset, self.request.query_params.get("ordering"))


class EditorWithFreshRoles(RequireRole):
    """Editors only, checked against the auth service's current roles, so a demotion or
    a disabled user applies at once."""

    role = Role.EDITOR
    fresh = True


class BrandDetailView(APIView):
    """GET is public. PATCH edits a brand's description and needs the editor role."""

    def get_authenticators(self):
        # Only the write looks at the Authorization header. DRF authenticates eagerly, so a
        # stale token on a public read would otherwise be a 401, or a 503 while auth is down.
        # Django's View.setup() has set self.request (the plain HttpRequest) by now.
        return [JWTAuthentication()] if self.request.method == "PATCH" else []

    def get_permissions(self):
        return [EditorWithFreshRoles()] if self.request.method == "PATCH" else []

    @staticmethod
    def _row(slug: str) -> dict:
        queryset = Brand.objects.with_stats().prefetch_related("industries", top_review_prefetch())
        return BrandDetailSerializer(get_object_or_404(queryset, slug=slug)).data

    def get(self, request, slug):
        return Response(self._row(slug))

    def patch(self, request, slug):
        brand = get_object_or_404(Brand.objects.only("id", "slug", "description"), slug=slug)
        serializer = BrandUpdateSerializer(brand, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info("brand %s edited by user %s", slug, request.user.id)
        return Response(self._row(slug))
