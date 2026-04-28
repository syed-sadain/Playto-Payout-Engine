from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home(request):
    return JsonResponse({"message": "Payout Engine API is running 🚀"})

def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "playto-payout-engine"
    })

urlpatterns = [
    path("", home),                      # root
    path("admin/", admin.site.urls),     # admin panel
    path("health/", health_check),       # health check

    # ✅ FIXED: correct API versioning
    path("api/v1/", include("payouts.urls")),
]