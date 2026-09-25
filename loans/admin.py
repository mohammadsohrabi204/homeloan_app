from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

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
class LoanPlanAdmin(admin.ModelAdmin):
    """
    فقط مدیر (is_staff=True) به این بخش دسترسی دارد — یعنی فقط مدیر می‌تواند
    مشخص کند چه وامی، با چه قیمت و قسطی تشکیل شود. کاربران عادی هیچ دسترسی‌ای
    به پنل مدیریت جنگو ندارند و فقط از صفحات عمومی سایت رزرو/پرداخت انجام می‌دهند.
    """

    list_display = ("title", "total_amount", "monthly_payment", "duration_months", "capacity_display", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title",)
    readonly_fields = ("created_by", "created_at")
    inlines = [ReservationInline]
    actions = ["action_start_plan"]
    fields = (
        "title", "description", "total_amount", "monthly_payment", "service_fee",
        "duration_months", "capacity", "payment_destination", "status", "start_date", "created_by", "created_at",
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

    @admin.display(description="ظرفیت پرشده")
    def capacity_display(self, obj):
        return f"{obj.confirmed_count} / {obj.capacity}"

    @admin.action(description="شروع طرح‌های انتخاب‌شده و ساخت اقساط برای همهٔ اعضا")
    def action_start_plan(self, request, queryset):
        for plan in queryset:
            try:
                start_loan_plan(plan)
                log_action(
                    request.user, "loan_plan_started", {"plan_id": plan.id},
                    request.META.get("REMOTE_ADDR"),
                )
                self.message_user(request, f"«{plan.title}» شروع شد و اقساط ساخته شدند.")
            except ValueError as exc:
                self.message_user(request, f"«{plan.title}»: {exc}", level="error")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("user", "loan_plan", "status", "has_won", "won_round", "reserved_at")
    list_filter = ("status", "has_won", "loan_plan")
    search_fields = ("user__full_name", "user__phone_number")
    autocomplete_fields = ["user", "loan_plan"]
    readonly_fields = ("user", "loan_plan", "status", "has_won", "won_round", "reserved_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reservation", "round_number", "amount", "jalali_due", "status", "gateway", "receipt_preview", "jalali_paid")
    list_display_links = ("reservation",)
    list_per_page = 25
    ordering = ("-receipt_submitted_at", "-id")
    list_filter = (ReceiptReviewFilter, "status", "gateway")
    search_fields = ("reservation__user__full_name", "reservation__user__phone_number")
    actions = ["action_confirm_payment", "action_reject_receipt"]
    readonly_fields = (
        "reservation", "round_number", "amount", "due_date", "status", "gateway",
        "gateway_authority", "gateway_ref", "receipt_link", "manual_reference", "receipt_submitted_at", "receipt_rejection_reason", "paid_at", "confirmed_by",
    )
    exclude = ("manual_receipt",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="رسید کارت‌به‌کارت")
    def receipt_status(self, obj):
        return "ارسال شده" if obj.manual_receipt else "—"

    @admin.display(description="مشاهدهٔ رسید")
    def receipt_preview(self, obj):
        if not obj.manual_receipt:
            return format_html('<span style="color:#777">بدون رسید</span>')
        url = f"/payment/receipt/{obj.id}/view/"
        return format_html(
            '<a href="{}" target="_blank" title="برای دیدن تصویر کامل کلیک کنید">'
            '<img src="{}" alt="رسید پرداخت" style="width:72px;height:52px;object-fit:cover;'
            'border:1px solid #bbb;border-radius:4px;vertical-align:middle"> '
            '<strong>مشاهده</strong></a>',
            url, url,
        )

    @admin.display(description="سررسید", ordering="due_date")
    def jalali_due(self, obj): return format_jalali(obj.due_date)

    @admin.display(description="زمان پرداخت", ordering="paid_at")
    def jalali_paid(self, obj): return format_jalali(obj.paid_at)

    @admin.display(description="تصویر رسید")
    def receipt_link(self, obj):
        if not obj.manual_receipt:
            return "—"
        return format_html('<a href="/payment/receipt/{}/view/" target="_blank">مشاهدهٔ امن رسید</a>', obj.id)

    @admin.action(description="تأیید دستی پرداخت‌های انتخاب‌شده (مثلاً واریز کارت‌به‌کارت)")
    def action_confirm_payment(self, request, queryset):
        updated = 0
        for payment in queryset.exclude(status=PaymentStatus.PAID).exclude(manual_receipt=""):
            payment.status = PaymentStatus.PAID
            payment.paid_at = timezone.now()
            payment.gateway = payment.gateway or "manual"
            payment.confirmed_by = request.user
            payment.save()
            log_action(
                request.user,
                "payment_manually_confirmed",
                {"payment_id": payment.id, "reservation_id": payment.reservation_id},
                request.META.get("REMOTE_ADDR"),
            )
            updated += 1
        self.message_user(request, f"{updated} قسطِ دارای رسید به‌صورت دستی تأیید شد.")

    @admin.action(description="رد رسیدهای انتخاب‌شده؛ کاربر می‌تواند رسید تازه ارسال کند")
    def action_reject_receipt(self, request, queryset):
        rejected = 0
        for payment in queryset.exclude(manual_receipt="").exclude(status=PaymentStatus.PAID):
            payment.status = PaymentStatus.RECEIPT_REJECTED
            payment.receipt_rejection_reason = "رسید توسط مدیر تأیید نشد. لطفاً واریز را بررسی و رسید جدید ارسال کنید."
            payment.save(update_fields=["status", "receipt_rejection_reason"])
            log_action(request.user, "manual_receipt_rejected", {"payment_id": payment.id, "reservation_id": payment.reservation_id}, request.META.get("REMOTE_ADDR"))
            rejected += 1
        self.message_user(request, f"{rejected} رسید رد شد؛ کاربران می‌توانند رسید تازه بفرستند.")


@admin.register(LotteryDraw)
class LotteryDrawAdmin(admin.ModelAdmin):
    list_display = ("loan_plan", "round_number", "jalali_scheduled", "status", "jalali_executed", "winner_reservation")
    list_filter = ("status", "loan_plan")
    readonly_fields = ("status", "executed_at", "winner_reservation", "eligible_snapshot", "integrity_hash", "created_by")
    fields = ("loan_plan", "round_number", "scheduled_at", "status", "executed_at", "winner_reservation", "eligible_snapshot", "integrity_hash", "created_by")
    actions = ["action_run_draw", "action_cancel_draw"]

    @admin.display(description="زمان اعلام", ordering="scheduled_at")
    def jalali_scheduled(self, obj): return format_jalali(obj.scheduled_at)

    @admin.display(description="زمان اجرا", ordering="executed_at")
    def jalali_executed(self, obj): return format_jalali(obj.executed_at)

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
