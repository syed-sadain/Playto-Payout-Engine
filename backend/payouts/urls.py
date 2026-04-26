from django.urls import path
from . import views

urlpatterns = [
    # Merchants
    path("merchants/", views.list_merchants, name="list-merchants"),
    path("merchants/<uuid:merchant_id>/", views.merchant_detail, name="merchant-detail"),
    path("merchants/<uuid:merchant_id>/ledger/", views.merchant_ledger, name="merchant-ledger"),

    # Payouts (nested under merchant)
    path(
        "merchants/<uuid:merchant_id>/payouts/",
        views.merchant_payouts,
        name="merchant-payouts",
    ),
    path(
        "merchants/<uuid:merchant_id>/payouts/<uuid:payout_id>/",
        views.payout_detail,
        name="payout-detail",
    ),

    # Flat payout endpoint per spec: POST /api/v1/payouts
    path("payouts/", views.payouts_flat, name="payouts-flat"),
]
