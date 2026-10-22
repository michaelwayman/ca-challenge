from django.db.models import Count, F
from django.views.generic import DetailView, TemplateView

from .models import Brand, Industry, Review

FEATURED_BRANDS = 6
RECENT_REVIEWS = 6


class HomeView(TemplateView):
    template_name = "catalog/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_brands"] = (
            Brand.objects.with_stats()
            .prefetch_related("industries")
            .order_by(F("average_rating").desc(nulls_last=True), "name")[:FEATURED_BRANDS]
        )
        context["recent_reviews"] = Review.objects.select_related("brand", "reviewer")[
            :RECENT_REVIEWS
        ]
        return context


class BrandListPageView(TemplateView):
    """Hosts <BrandList />. The industries ride along as JSON so the filter needs no
    second request; the server-rendered cards are the no-JavaScript fallback."""

    template_name = "catalog/brand_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # order_by is explicit: a model's default ordering is ignored once a query aggregates.
        context["industries"] = list(
            Industry.objects.annotate(brand_count=Count("brands"))
            .order_by("name")
            .values("name", "slug", "brand_count")
        )
        context["brands"] = Brand.objects.with_stats().prefetch_related("industries")
        return context


class BrandDetailView(DetailView):
    queryset = Brand.objects.with_stats().prefetch_related("industries")
    template_name = "catalog/brand_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reviews"] = self.object.reviews.select_related("reviewer")
        return context


class ReviewDetailView(DetailView):
    queryset = Review.objects.select_related("brand", "reviewer")
    template_name = "catalog/review_detail.html"
