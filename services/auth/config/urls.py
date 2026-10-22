from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from accounts import views


def healthz(request):
    return JsonResponse({"status": "ok"})


# The API is versioned in the path so a v2 can run beside v1 until its clients move.
urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path(".well-known/jwks.json", views.jwks),
    path("api/auth/v1/token/", views.TokenView.as_view(), name="token"),
    path("api/auth/v1/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("api/auth/v1/introspect/", views.IntrospectView.as_view(), name="introspect"),
]
