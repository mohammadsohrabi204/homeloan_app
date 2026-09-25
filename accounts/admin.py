from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["phone_number"]
    list_display = ["phone_number", "full_name", "is_staff", "is_active", "is_2fa_enabled", "date_joined"]
    list_filter = ["is_staff", "is_active", "is_2fa_enabled"]
    search_fields = ["phone_number", "full_name", "national_id"]

    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("اطلاعات شخصی", {"fields": ("full_name", "national_id")}),
        ("دسترسی‌ها", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("امنیت", {"fields": ("is_2fa_enabled",)}),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone_number", "full_name", "password1", "password2", "is_staff"),
            },
        ),
    )
    readonly_fields = ["last_login", "date_joined", "is_2fa_enabled"]
