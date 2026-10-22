from django.urls import path

from . import views

# Paths mirror the WordPress permalinks (/brand/<slug>/, /review/<slug>/, /review/page/<n>/,
# /<page-slug>/). The static-page catch-all must stay last so it never shadows a route above.
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("brand/", views.BrandListPageView.as_view(), name="brand-list"),
    path("brand/<slug:slug>/", views.BrandDetailView.as_view(), name="brand-detail"),
    path("review/", views.review_list, name="review-list"),
    path("review/page/<int:page>/", views.review_list, name="review-list-page"),
    path("review/<slug:slug>/", views.ReviewDetailView.as_view(), name="review-detail"),
    path("<slug:slug>/", views.PageDetailView.as_view(), name="page-detail"),
]
