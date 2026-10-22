from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),  # before the catch-all static-page route
    path("api/", include("catalog.api.urls")),
    path("", include("catalog.urls")),
]
