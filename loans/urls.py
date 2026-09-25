from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("manager/plans/new/", views.manager_plan_create, name="manager_plan_create"),
    path("manager/plans/<int:plan_id>/edit/", views.manager_plan_edit, name="manager_plan_edit"),
    path("manager/plans/<int:plan_id>/start/", views.manager_plan_start, name="manager_plan_start"),
    path("manager/destinations/", views.manager_destination_list, name="manager_destinations"),
    path("manager/destinations/new/", views.manager_destination_create, name="manager_destination_create"),
    path("manager/draws/new/", views.manager_draw_create, name="manager_draw_create"),
    path("manager/draws/<int:draw_id>/run/", views.manager_draw_run, name="manager_draw_run"),
    path("manager/settings/", views.manager_settings, name="manager_settings"),
    path("manager/users/", views.manager_users, name="manager_users"),
    path("notifications/", views.notifications, name="notifications"),
    path("manager/payments/<int:payment_id>/action/", views.manager_payment_action, name="manager_payment_action"),
    path("plans/<int:plan_id>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:plan_id>/reserve/", views.reserve, name="reserve"),
]
