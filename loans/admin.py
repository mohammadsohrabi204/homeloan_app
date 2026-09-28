from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django import forms

from .models import AuditLog, FundSettings, LoanPlan, LotteryDraw, LotteryStatus, Notification, Payment, PaymentDestination, PaymentStatus, PlanStatus, Reservation
from .jalali import format_jalali
from .services import log_action, run_lottery_draw, start_loan_plan


class ReservationInline(admin.TabularInline):
    model = Reservation
    extra = 0
    fields = ("user", "status", "has_won", "won_round", "reserved_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ReceiptReviewFilter(admin.SimpleListFilter):
    title = "بررسی رسید"
    parameter_name = "receipt_review"

    def lookups(self, request, model_admin):
        return [
            ("pending", "رسیدهای منتظر بررسی"),
            ("submitted", "همهٔ رسیدهای ارسال‌شده"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.exclude(manual_receipt="").exclude(status=PaymentStatus.PAID)
        if self.value() == "submitted":
            return queryset.exclude(manual_receipt="")
        return queryset


@admin.register(PaymentDestination)
class PaymentDestinationAdmin(admin.ModelAdmin):
    list_display = ("title", "account_holder", "card_number", "iban", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "account_holder", "card_number", "iban")


@admin.register(LoanPlan)
class LoanPlanManagerForm(forms.ModelForm):
    start_date = forms.CharField(label="تاریخ شروع (شمسی)", widget=forms.TextInput(attrs={
        "type": "text", "placeholder": "۱۴۰۵/۰۷/۰۳", "inputmode": "numeric", "class": "jalali-date-input"
    }))
    total_amount = forms.DecimalField(label="مبلغ وام", widget=forms.NumberInput(attrs={"class": "amount-input"}))
    monthly_payment = forms.DecimalField(label="قسط ماهانه", widget=forms.NumberInput(attrs={"class": "amount-input"}))
    service_fee = forms.DecimalField(label="هزینه خدمات", widget=forms.NumberInput(attrs={"class": "amount-input"}))

    class Meta:
        model = LoanPlan
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.start_date:
            from .jalali import gregorian_to_jalali
            y,m,d = gregorian_to_jalali(self.instance.start_date.year, self.instance.start_date.month, self.instance.start_date.day)
            self.initial["start_date"] = f"{y:04d}/{m:02d}/{d:02d}"

    def clean_start_date(self):
        from .jalali import jalali_to_gregorian
        raw = str(self.cleaned_data["start_date"]).strip().replace("-", "/")
        try:
            y,m,d = [int(x) for x in raw.split("/")]
            gy,gm,gd = jalali_to_gregorian(y,m,d)
            from datetime import date
            return date(gy,gm,gd)
        except (ValueError,TypeError):
            raise forms.ValidationError("تاریخ را به صورت ۱۴۰۵/۰۷/۰۳ وارد کنید.")

    class Media:
        js = ("js/manager_amount_words.js",)

class LoanPlanAdmin(admin.ModelAdmin):
    """
    فقط مدیر (is_staff=True) به این بخش دسترسی دارد — یعنی فقط مدیر می‌تواند
    مشخص کند چه وامی، با چه قیمت و قسطی تشکیل شود. کاربران عادی هیچ دسترسی‌ای
    به پنل مدیریت جنگو ندارند و فقط از صفحات عمومی سایت رزرو/پرداخت انجام می‌دهند.
    """

    list_display = ("title", "total_amount_display", "monthly_payment_display", "service_fee_display", "duration_months", "capacity_display", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title",)
    readonly_fields = ("created_by", "created_at")
    inlines = [ReservationInline]
    actions = ["action_start_plan"]
    fields = (
        "title", "description", "total_amount", "monthly_payment", "service_fee", "start_date",
        "duration_months", "capacity", "payment_destination", "status", "created_by", "created_at",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if not change:
            log_action(
                request.user, "loan_plan_created", {"plan_id": obj.id, "title": obj.title},
                request.META.get("REMOTE_ADDR"),
            )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in (PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED, PlanStatus.CANCELLED):
            # پس از شروع، تغییر مبلغ/مدت/ظرفیت جدول اقساط و سوابق مالی را ناسازگار می‌کند.
            return tuple(self.readonly_fields) + (
                "title", "description", "total_amount", "monthly_payment", "service_fee",
                "duration_months", "capacity", "status", "start_date",
            )
        return self.readonly_fields

    form = LoanPlanManagerForm


    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if not change:
            log_action(
                request.user, "lottery_scheduled",
                {"draw_id": obj.id, "plan_id": obj.loan_plan_id, "round": obj.round_number},
                request.META.get("REMOTE_ADDR"),
            )

    @admin.action(description="برگزاری قرعه‌کشی برای موارد زمان‌بندی‌شدهٔ انتخاب‌شده")
    def action_run_draw(self, request, queryset):
        for draw in queryset.filter(status="scheduled"):
            try:
                winner = run_lottery_draw(draw, actor=request.user)
                self.message_user(request, f"دورهٔ {draw.round_number} «{draw.loan_plan}» — برنده: {winner.user.full_name}")
            except ValueError as exc:
                self.message_user(request, f"دورهٔ {draw.round_number}: {exc}", level="error")

    @admin.action(description="لغو قرعه‌کشی‌های زمان‌بندی‌شدهٔ انتخاب‌شده")
    def action_cancel_draw(self, request, queryset):
        for draw in queryset.filter(status=LotteryStatus.SCHEDULED):
            draw.status = LotteryStatus.CANCELLED
            draw.save(update_fields=["status"])
            log_action(
                request.user, "lottery_cancelled", {"draw_id": draw.id, "plan_id": draw.loan_plan_id},
                request.META.get("REMOTE_ADDR"),
            )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("jalali_created", "actor", "action", "ip_address")
    list_filter = ("action",)
    search_fields = ("action", "details", "actor__full_name", "actor__phone_number")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    @admin.display(description="زمان", ordering="created_at")
    def jalali_created(self, obj): return format_jalali(obj.created_at)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FundSettings)
class FundSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("اطلاعات عمومی", {"fields": ("fund_name", "support_phone", "support_text", "is_active")}),
        ("متن‌های قابل نمایش به کاربران", {"fields": ("payment_instructions", "terms_text")}),
        ("سیستم", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not FundSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__full_name", "user__phone_number", "title", "message")
    readonly_fields = ("user", "title", "message", "kind", "payment", "lottery_draw", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
