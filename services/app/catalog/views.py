from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, F
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, TemplateView

from .models import Brand, Industry, Page, Review

FEATURED_BRANDS = 6
RECENT_REVIEWS = 6
REVIEWS_PER_PAGE = 10  # WordPress's posts_per_page for this site, so the pages line up


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


def review_list(request, page=1):
    """The reviews archive: /review/ and /review/page/<n>/, ten to a page, as in WordPress."""
    if page == 1 and request.path != reverse("review-list"):
        return redirect("review-list", permanent=True)  # /review/page/1/ is just /review/
    paginator = Paginator(Review.objects.select_related("brand", "reviewer"), REVIEWS_PER_PAGE)
    try:
        page_obj = paginator.page(page)
    except EmptyPage as exc:
        raise Http404("No such page.") from exc
    # First, last, and the current page with its neighbours; None marks a gap.
    page_items = [
        None if n == paginator.ELLIPSIS else n
        for n in paginator.get_elided_page_range(page, on_each_side=1, on_ends=1)
    ]
    return render(
        request, "catalog/review_list.html", {"page_obj": page_obj, "page_items": page_items}
    )


class PageDetailView(DetailView):
    """A static page at /<slug>/ (About, Contact, ...)."""

    queryset = Page.objects.all()
    template_name = "catalog/page_detail.html"
