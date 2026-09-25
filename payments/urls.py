from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pay/<int:payment_id>/", views.pay, name="pay"),
    path("callback/<int:payment_id>/", views.callback, name="callback"),
    path("receipt/<int:payment_id>/", views.submit_manual_receipt, name="submit_manual_receipt"),
    path("receipt/<int:payment_id>/view/", views.view_manual_receipt, name="view_manual_receipt"),
]
