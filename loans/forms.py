from django import forms
from django.contrib.auth import get_user_model

from .jalali import gregorian_to_jalali, jalali_to_gregorian
from .models import (
    FundSettings,
    LoanPlan,
    LotteryDraw,
    PaymentDestination,
)


class ManagerLoanPlanForm(forms.ModelForm):
    start_date = forms.CharField(
        label="تاریخ شروع (شمسی)",
        required=True,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "placeholder": "۱۴۰۵/۰۷/۰۳",
                "inputmode": "numeric",
                "autocomplete": "off",
                "maxlength": "10",
                "class": "jalali-date-input",
                "dir": "ltr",
            }
        ),
    )

    class Meta:
        model = LoanPlan
        fields = (
            "title",
            "description",
            "total_amount",
            "monthly_payment",
            "service_fee",
            "duration_months",
            "capacity",
            "payment_destination",
            "status",
            "start_date",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [("draft", "پیش‌نویس (هنوز نمایش داده نمی‌شود)"), ("open", "باز برای رزرو")]
        if self.instance and self.instance.status in ("draft", "open"):
            self.initial["status"] = self.instance.status
        elif self.instance and self.instance.status:
            self.fields["status"].disabled = True

        if self.instance and self.instance.start_date:
            gy = self.instance.start_date.year
            gm = self.instance.start_date.month
            gd = self.instance.start_date.day
            jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
            self.initial["start_date"] = f"{jy:04d}/{jm:02d}/{jd:02d}"

    def clean_start_date(self):
        raw = str(self.cleaned_data.get("start_date", "")).strip()
        if not raw:
            raise forms.ValidationError("تاریخ شروع الزامی است.")

        # Accept Persian/Arabic digits and common separators so the field
        # remains fully editable on desktop and mobile keyboards.
        translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        raw = raw.translate(translation).replace("-", "/").replace(".", "/")
        try:
            parts = [part.strip() for part in raw.split("/")]
            if len(parts) != 3 or not all(parts):
                raise ValueError
            y, m, d = (int(part) for part in parts)
            if y < 1 or not 1 <= m <= 12:
                raise ValueError
            if m <= 6:
                max_day = 31
            elif m <= 11:
                max_day = 30
            else:
                # jalali_to_gregorian validates the final Esfand day through
                # the resulting Gregorian date round-trip below.
                max_day = 30
            if not 1 <= d <= max_day:
                raise ValueError

            gy, gm, gd = jalali_to_gregorian(y, m, d)
            from datetime import date
            converted = date(gy, gm, gd)

            # Round-trip check catches invalid Esfand dates.
            jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
            if (jy, jm, jd) != (y, m, d):
                raise ValueError
            return converted
        except (ValueError, TypeError, OverflowError):
            raise forms.ValidationError(
                "تاریخ را به صورت ۱۴۰۵/۰۷/۰۳ وارد کنید."
            )


class PaymentDestinationForm(forms.ModelForm):
    class Meta:
        model = PaymentDestination
        fields = (
            "title",
            "account_holder",
            "card_number",
            "iban",
            "is_active",
        )
        widgets = {
            "card_number": forms.TextInput(
                attrs={"inputmode": "numeric", "maxlength": "16"}
            ),
            "iban": forms.TextInput(
                attrs={"inputmode": "text", "maxlength": "26"}
            ),
        }

    def clean_card_number(self):
        value = self.cleaned_data.get("card_number", "").replace(" ", "").replace("-", "")
        if value and (not value.isdigit() or len(value) != 16):
            raise forms.ValidationError("شماره کارت باید ۱۶ رقم باشد.")
        return value

    def clean_iban(self):
        value = self.cleaned_data.get("iban", "").replace(" ", "").upper()
        if value and value.startswith("IR"):
            if len(value) != 26 or not value[2:].isdigit():
                raise forms.ValidationError("شماره شبا باید به صورت IR و ۲۴ رقم وارد شود.")
        elif value:
            if len(value) != 24 or not value.isdigit():
                raise forms.ValidationError("شماره شبا باید ۲۴ رقم باشد یا با IR شروع شود.")
            value = f"IR{value}"
        return value


class ManagerLotteryDrawForm(forms.ModelForm):
    class Meta:
        model = LotteryDraw
        fields = (
            "loan_plan",
            "round_number",
            "scheduled_at",
        )
        widgets = {
            "scheduled_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan_plan"].queryset = LoanPlan.objects.all().order_by("-created_at")
        self.fields["scheduled_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
        ]

    def clean(self):
        cleaned = super().clean()
        plan = cleaned.get("loan_plan")
        round_number = cleaned.get("round_number")

        if plan and round_number:
            if round_number > plan.duration_months:
                self.add_error(
                    "round_number",
                    "شماره دوره از تعداد دوره‌های طرح بیشتر است.",
                )
            if LotteryDraw.objects.filter(
                loan_plan=plan,
                round_number=round_number,
            ).exclude(pk=self.instance.pk).exists():
                self.add_error(
                    "round_number",
                    "برای این طرح و این دوره قبلاً قرعه‌کشی ثبت شده است.",
                )

        return cleaned


class FundSettingsForm(forms.ModelForm):
    class Meta:
        model = FundSettings
        fields = (
            "fund_name",
            "support_phone",
            "support_text",
            "payment_instructions",
            "terms_text",
            "is_active",
        )
        widgets = {
            "support_text": forms.Textarea(attrs={"rows": 2}),
            "payment_instructions": forms.Textarea(attrs={"rows": 5}),
            "terms_text": forms.Textarea(attrs={"rows": 6}),
        }


User = get_user_model()


class ManagerUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "full_name",
            "phone_number",
            "national_id",
            "card_number",
            "iban",
            "phone_verified",
            "is_active",
            "is_staff",
            "is_2fa_enabled",
        )
