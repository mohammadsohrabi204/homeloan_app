import json

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

from .jalali import format_jalali


class PlanStatus(models.TextChoices):
    DRAFT = "draft", "پیش‌نویس (هنوز نمایش داده نمی‌شود)"
    OPEN = "open", "باز برای رزرو"
    FULL = "full", "تکمیل ظرفیت"
    IN_PROGRESS = "in_progress", "در حال اجرا"
    COMPLETED = "completed", "پایان‌یافته"
    CANCELLED = "cancelled", "لغوشده"


class ReservationStatus(models.TextChoices):
    CONFIRMED = "confirmed", "تأییدشده"
    CANCELLED = "cancelled", "لغوشده"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "در انتظار پرداخت"
    PAID = "paid", "پرداخت‌شده"
    RECEIPT_REJECTED = "receipt_rejected", "رسید رد شده"
    FAILED = "failed", "ناموفق"


class LotteryStatus(models.TextChoices):
    SCHEDULED = "scheduled", "زمان‌بندی‌شده"
    COMPLETED = "completed", "برگزارشده"
    CANCELLED = "cancelled", "لغوشده"


class PaymentDestination(models.Model):
    """حسابی که مدیر برای دریافت اقساط یک طرح معرفی می‌کند."""
    title = models.CharField("عنوان حساب", max_length=100)
    account_holder = models.CharField("نام صاحب حساب", max_length=120)
    card_number = models.CharField("شماره کارت", max_length=16, blank=True)
    iban = models.CharField("شماره شبا", max_length=26, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "حساب دریافت اقساط"
        verbose_name_plural = "حساب‌های دریافت اقساط"

    def __str__(self):
        return f"{self.title} — {self.account_holder}"


class LoanPlan(models.Model):
    title = models.CharField("عنوان وام", max_length=150)
    description = models.TextField("توضیحات", blank=True)

    total_amount = models.DecimalField("مبلغ کل وام (تومان)", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    monthly_payment = models.DecimalField("قسط ماهانه هر عضو (تومان)", max_digits=14, decimal_places=0, validators=[MinValueValidator(1)])
    service_fee = models.DecimalField(
        "هزینهٔ خدمات صندوق (تومان)", max_digits=14, decimal_places=0, default=0,
        help_text="هزینهٔ اداره صندوق، نه سود/بهره — این صندوق قرض‌الحسنه (بدون سود) است. "
                  "یک‌بارمصرف است و به قسطِ دورهٔ اول هر عضو اضافه می‌شود.", validators=[MinValueValidator(0)],
    )
    duration_months = models.PositiveIntegerField("تعداد دوره / ماه", validators=[MinValueValidator(1)], help_text="هم تعداد اقساط و هم تعداد قرعه‌کشی‌های این طرح.")
    capacity = models.PositiveIntegerField("ظرفیت (حداکثر تعداد عضو)", validators=[MinValueValidator(1)])

    status = models.CharField(max_length=20, choices=PlanStatus.choices, default=PlanStatus.OPEN)
    start_date = models.DateField("تاریخ شروع", null=True, blank=True)
    payment_destination = models.ForeignKey(
        PaymentDestination, on_delete=models.PROTECT, null=True, blank=True,
        related_name="loan_plans", verbose_name="حساب دریافت اقساط",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_plans", verbose_name="ایجادشده توسط"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طرح وام"
        verbose_name_plural = "طرح‌های وام"
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gt=0), name="loan_total_amount_positive"),
            models.CheckConstraint(condition=models.Q(monthly_payment__gt=0), name="loan_monthly_payment_positive"),
            models.CheckConstraint(condition=models.Q(service_fee__gte=0), name="loan_service_fee_nonnegative"),
            models.CheckConstraint(condition=models.Q(duration_months__gt=0), name="loan_duration_positive"),
            models.CheckConstraint(condition=models.Q(capacity__gt=0), name="loan_capacity_positive"),
        ]

    def __str__(self):
        return self.title

    @property
    def confirmed_count(self):
        return self.reservations.filter(status=ReservationStatus.CONFIRMED).count()

    @property
    def slots_left(self):
        return max(self.capacity - self.confirmed_count, 0)


class Reservation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations")
    loan_plan = models.ForeignKey(LoanPlan, on_delete=models.CASCADE, related_name="reservations")
    status = models.CharField(max_length=20, choices=ReservationStatus.choices, default=ReservationStatus.CONFIRMED)

    has_won = models.BooleanField("برندهٔ قرعه‌کشی شده", default=False)
    won_round = models.PositiveIntegerField("دورهٔ برد", null=True, blank=True)
    payout_confirmed_at = models.DateTimeField(
        "تأیید واریز وام توسط مدیر", null=True, blank=True,
        help_text="زمانی که مدیر، واریز مبلغ وام به حساب برنده را تأیید می‌کند.",
    )

    reserved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "loan_plan"], name="uq_user_plan")]
        verbose_name = "رزرو"
        verbose_name_plural = "رزروها"

    def __str__(self):
        return f"{self.user} - {self.loan_plan}"

    @property
    def jalali_payout_confirmed_at(self):
        return format_jalali(self.payout_confirmed_at)


class Payment(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="payments")
    round_number = models.PositiveIntegerField("شمارهٔ دوره")
    amount = models.DecimalField("مبلغ (تومان)", max_digits=14, decimal_places=0)
    due_date = models.DateField("سررسید", null=True, blank=True)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    gateway = models.CharField(max_length=30, blank=True)
    gateway_authority = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_ref = models.CharField(max_length=100, blank=True)
    manual_receipt = models.ImageField(
        "تصویر رسید کارت‌به‌کارت", upload_to="payment_receipts/%Y/%m/", blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    manual_reference = models.CharField("شمارهٔ پیگیری واریز", max_length=80, blank=True)
    receipt_submitted_at = models.DateTimeField("زمان ارسال رسید", null=True, blank=True)
    receipt_rejection_reason = models.CharField("علت رد رسید", max_length=250, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="confirmed_payments", verbose_name="تأییدشده توسط (تأیید دستی)",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["reservation", "round_number"], name="uq_reservation_round")]
        ordering = ["round_number"]
        verbose_name = "قسط"
        verbose_name_plural = "اقساط"

    def __str__(self):
        return f"{self.reservation} - دورهٔ {self.round_number}"

    @property
    def jalali_due_date(self):
        return format_jalali(self.due_date)


class LotteryDraw(models.Model):
    loan_plan = models.ForeignKey(LoanPlan, on_delete=models.CASCADE, related_name="lottery_draws")
    round_number = models.PositiveIntegerField("شمارهٔ دوره", validators=[MinValueValidator(1)])
    scheduled_at = models.DateTimeField("زمان اعلام‌شدهٔ قرعه‌کشی")
    status = models.CharField(max_length=20, choices=LotteryStatus.choices, default=LotteryStatus.SCHEDULED)
    executed_at = models.DateTimeField(null=True, blank=True)

    winner_reservation = models.ForeignKey(
        Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="رزروِ برنده"
    )
    eligible_snapshot = models.TextField(blank=True, help_text="فهرست رزروهای واجدشرایط در لحظهٔ قرعه‌کشی (برای رسیدگی به اعتراض)")
    integrity_hash = models.CharField(max_length=64, blank=True, help_text="اثر انگشت SHA-256 برای اثبات عدم دستکاری بعدی")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_draws")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["loan_plan", "round_number"], name="uq_plan_round"),
            models.CheckConstraint(condition=models.Q(round_number__gt=0), name="lottery_round_positive"),
        ]
        ordering = ["round_number"]
        verbose_name = "قرعه‌کشی"
        verbose_name_plural = "قرعه‌کشی‌ها"

    def __str__(self):
        return f"{self.loan_plan} - دورهٔ {self.round_number}"

    def eligible_ids(self):
        return json.loads(self.eligible_snapshot) if self.eligible_snapshot else []

    @property
    def jalali_scheduled_at(self):
        return format_jalali(self.scheduled_at)

    @property
    def jalali_executed_at(self):
        return format_jalali(self.executed_at)

    def clean(self):
        super().clean()
        if self.loan_plan_id and self.round_number > self.loan_plan.duration_months:
            from django.core.exceptions import ValidationError
            raise ValidationError({"round_number": "شمارهٔ دوره نمی‌تواند از تعداد دوره‌های طرح بیشتر باشد."})


class AuditLog(models.Model):
    """
    ثبت رویدادهای حساس (ورود، ساخت وام، اجرای قرعه‌کشی، تأیید پرداخت و ...) برای شفافیت و رسیدگی به اختلاف.
    این جدول را نمی‌توان از پنل مدیریت ویرایش یا حذف کرد.
    """

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "رویداد امنیتی"
        verbose_name_plural = "گزارش رویدادها"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.action}"
