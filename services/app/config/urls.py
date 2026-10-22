from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz),
    path("api/", include("catalog.api.urls")),
    path("", include("catalog.urls")),
]
