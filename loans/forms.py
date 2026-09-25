from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import FundSettings, LoanPlan, LotteryDraw, PaymentDestination, PlanStatus


class ManagerLoanPlanForm(forms.ModelForm):
    class Meta:
        model = LoanPlan
        fields = (
            "title", "description", "total_amount", "monthly_payment",
            "service_fee", "duration_months", "capacity", "payment_destination",
            "status", "start_date",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
        }

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
    class Meta:
        model = LotteryDraw
        fields = ("loan_plan", "round_number", "scheduled_at")
        widgets = {"scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

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
