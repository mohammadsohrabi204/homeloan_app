from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("plans/<int:plan_id>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:plan_id>/reserve/", views.reserve, name="reserve"),
]
