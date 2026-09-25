from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("notifications/", views.notifications, name="notifications"),
    path("manager/payments/<int:payment_id>/action/", views.manager_payment_action, name="manager_payment_action"),
    path("plans/<int:plan_id>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:plan_id>/reserve/", views.reserve, name="reserve"),
]
