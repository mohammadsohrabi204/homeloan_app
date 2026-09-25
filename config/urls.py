from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "پنل مدیریت صندوق وام خانگی"
admin.site.site_title = "مدیریت صندوق وام"
admin.site.index_title = "خوش آمدید — مدیریت طرح‌های وام، اقساط و قرعه‌کشی"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("payment/", include("payments.urls")),
    path("", include("loans.urls")),
]
