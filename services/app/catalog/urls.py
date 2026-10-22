from django.urls import path

from . import views

# Paths mirror the WordPress permalinks (/brand/<slug>/, /review/<slug>/).
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("brand/", views.BrandListPageView.as_view(), name="brand-list"),
    path("brand/<slug:slug>/", views.BrandDetailView.as_view(), name="brand-detail"),
    path("review/<slug:slug>/", views.ReviewDetailView.as_view(), name="review-detail"),
]
