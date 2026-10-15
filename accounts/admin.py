from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User
from loans.jalali import format_jalali


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["phone_number"]
    list_display = ["phone_number", "full_name", "is_staff", "is_active", "is_2fa_enabled", "jalali_date_joined"]
    list_filter = ["is_staff", "is_active", "is_2fa_enabled"]
    search_fields = ["phone_number", "full_name", "national_id"]

    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("اطلاعات شخصی", {"fields": ("full_name", "national_id")}),
        ("دسترسی‌ها", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("امنیت", {"fields": ("is_2fa_enabled",)}),
        ("تاریخ‌ها", {"fields": ("jalali_last_login", "jalali_date_joined")}),
    )
    @admin.display(description="آخرین ورود (شمسی)", ordering="last_login")
    def jalali_last_login(self, obj): return format_jalali(obj.last_login) if obj and obj.last_login else "—"

    @admin.display(description="تاریخ عضویت (شمسی)", ordering="date_joined")
    def jalali_date_joined(self, obj): return format_jalali(obj.date_joined) if obj and obj.date_joined else "—"

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone_number", "full_name", "password1", "password2", "is_staff"),
            },
        ),
    )
    readonly_fields = ["jalali_last_login", "jalali_date_joined", "is_2fa_enabled"]
