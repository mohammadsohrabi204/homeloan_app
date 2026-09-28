from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime
from .jalali import jalali_to_gregorian, gregorian_to_jalali

from .models import FundSettings, LoanPlan, LotteryDraw, PaymentDestination, PlanStatus
from .jalali import jalali_to_gregorian


class ManagerLoanPlanForm(forms.ModelForm):
    start_date = forms.CharField(
        label="تاریخ شروع (شمسی)",
        required=True,
        widget=forms.TextInput(attrs={"type": "text", "placeholder": "۱۴۰۵/۰۷/۰۳", "inputmode": "numeric", "class": "jalali-date-input"}),
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.start_date:
            gy, gm, gd = self.instance.start_date.year, self.instance.start_date.month, self.instance.start_date.day
            jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
            self.initial["start_date"] = f"{jy:04d}/{jm:02d}/{jd:02d}"

    class Meta:
        model = LoanPlan
        fields = (
            "title", "description", "total_amount", "monthly_payment",
            "service_fee", "duration_months", "capacity", "payment_destination",
            "status", "start_date",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_start_date(self):
        raw = str(self.cleaned_data.get("start_date", "")).strip().replace("-", "/")
        if not raw:
            raise forms.ValidationError("تاریخ شروع الزامی است.")
        try:
            y, m, d = [int(x) for x in raw.split("/")]
            gy, gm, gd = jalali_to_gregorian(y, m, d)
            from datetime import date
            return date(gy, gm, gd)
        except (ValueError, TypeError):
            raise forms.ValidationError("تاریخ را به صورت ۱۴۰۵/۰۷/۰۳ وارد کنید.")

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        if status in (PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED, PlanStatus.CANCELLED):
            if self.instance.pk and self.instance.status != status:
                raise forms.ValidationError("طرحی که وارد مرحله اجرا شده، از این فرم قابل تغییر وضعیت نیست.")
        return cleaned


class PaymentDestinationForm(forms.ModelForm):
    class Meta:
        model = PaymentDestination
        fields = ("title", "account_holder", "card_number", "iban", "is_active")


class ManagerLotteryDrawForm(forms.ModelForm):
    scheduled_at = forms.CharField(
        label="زمان قرعه‌کشی (شمسی)",
        required=True,
        widget=forms.TextInput(attrs={
            "type": "text",
            "placeholder": "۱۴۰۵/۰۷/۰۳ ۲۰:۳۰",
            "inputmode": "numeric",
            "class": "jalali-date-input",
        }),
    )

    class Meta:
        model = LotteryDraw
        fields = ("loan_plan", "round_number", "scheduled_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.scheduled_at:
            value = timezone.localtime(self.instance.scheduled_at)
            jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
            self.initial["scheduled_at"] = f"{jy:04d}/{jm:02d}/{jd:02d} {value:%H:%M}"

    def clean_scheduled_at(self):
        raw = str(self.cleaned_data.get("scheduled_at", "")).strip().replace("-", "/")
        try:
            date_part, time_part = raw.split()
            y, m, d = [int(x) for x in date_part.split("/")]
            hour, minute = [int(x) for x in time_part.split(":")[:2]]
            gy, gm, gd = jalali_to_gregorian(y, m, d)
            value = timezone.make_aware(datetime(gy, gm, gd, hour, minute), timezone.get_current_timezone())
        except (ValueError, TypeError):
            raise forms.ValidationError("زمان را به صورت ۱۴۰۵/۰۷/۰۳ ۲۰:۳۰ وارد کنید.")
        if value <= timezone.now():
            raise forms.ValidationError("زمان قرعه‌کشی باید در آینده باشد.")
        return value

    def clean(self):
        cleaned = super().clean()
        plan = cleaned.get("loan_plan")
        round_number = cleaned.get("round_number")
        if plan and round_number:
            if round_number > plan.duration_months:
                raise forms.ValidationError("شماره دوره از تعداد دوره‌های طرح بیشتر است.")
            qs = LotteryDraw.objects.filter(loan_plan=plan, round_number=round_number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("برای این طرح و این دوره قبلاً قرعه‌کشی ثبت شده است.")
        return cleaned

    def clean(self):
        cleaned = super().clean()
        plan = cleaned.get("loan_plan")
        round_number = cleaned.get("round_number")
        if plan and round_number:
            if round_number > plan.duration_months:
                raise forms.ValidationError("شماره دوره از تعداد دوره‌های طرح بیشتر است.")
            if LotteryDraw.objects.filter(loan_plan=plan, round_number=round_number).exists():
                raise forms.ValidationError("برای این طرح و این دوره قبلاً قرعه‌کشی ثبت شده است.")
        if cleaned.get("scheduled_at") and cleaned["scheduled_at"] <= timezone.now():
            raise forms.ValidationError("زمان قرعه‌کشی باید در آینده باشد.")
        return cleaned


class FundSettingsForm(forms.ModelForm):
    class Meta:
        model = FundSettings
        fields = ("fund_name", "support_phone", "support_text", "payment_instructions", "terms_text", "is_active")
        widgets = {
            "support_text": forms.Textarea(attrs={"rows": 2}),
            "payment_instructions": forms.Textarea(attrs={"rows": 5}),
            "terms_text": forms.Textarea(attrs={"rows": 6}),
        }


User = get_user_model()


class ManagerUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "phone_number", "national_id", "card_number", "iban", "phone_verified", "is_active", "is_staff", "is_2fa_enabled")
