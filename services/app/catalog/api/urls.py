from django.urls import path

from .views import BrandDetailView, BrandListView

urlpatterns = [
    path("brands/", BrandListView.as_view(), name="api-brand-list"),
    path("brands/<slug:slug>/", BrandDetailView.as_view(), name="api-brand-detail"),
]
