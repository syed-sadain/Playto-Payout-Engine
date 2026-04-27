from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home(request):
    return JsonResponse({"message": "Payout Engine API is running 🚀"})

def health_check(request):
    return JsonResponse({"status": "ok", "service": "playto-payout-engine"})

urlpatterns = [
    path("", home),                      # ✅ root URL
    path("admin/", admin.site.urls),     # ✅ admin panel
    path("health/", health_check),       # ✅ health check
    path("api/v1/", include("payouts.urls")),  # ✅ API routes
]