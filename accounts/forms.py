from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator

from .models import User

phone_validator = RegexValidator(
    regex=r"^09\d{9}$", message="شماره موبایل معتبر نیست (مثال: 09123456789)."
)


class RegisterForm(forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=120, min_length=3)
    phone_number = forms.CharField(label="شماره موبایل", validators=[phone_validator])
    national_id = forms.CharField(
        label="کد ملی (اختیاری)", required=False, min_length=10, max_length=10
    )
    card_number = forms.CharField(label="شماره کارت برای دریافت وام", min_length=16, max_length=16)
    iban = forms.CharField(label="شماره شبا برای دریافت وام", min_length=24, max_length=26)
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="تکرار رمز عبور", widget=forms.PasswordInput)

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("این شماره موبایل قبلاً ثبت‌نام کرده است.")
        return phone

    def clean_national_id(self):
        national_id = self.cleaned_data.get("national_id", "").strip()
        if national_id and User.objects.filter(national_id=national_id).exists():
            raise forms.ValidationError("این کد ملی قبلاً ثبت شده است.")
        return national_id or None

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        try:
            # قوانین قدرت رمز عبور جنگو را اعمال می‌کند (طول، رمزهای رایج، شباهت به اطلاعات کاربر و...)
            validate_password(password)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password

    def clean_card_number(self):
        card = self.cleaned_data["card_number"].replace("-", "").replace(" ", "")
        if not card.isdigit() or len(card) != 16:
            raise forms.ValidationError("شماره کارت باید ۱۶ رقم باشد.")
        digits = [int(char) for char in card]
        total = sum((digit * (2 if index % 2 == 0 else 1)) - (9 if digit * (2 if index % 2 == 0 else 1) > 9 else 0) for index, digit in enumerate(digits))
        if total % 10:
            raise forms.ValidationError("شماره کارت معتبر نیست.")
        return card

    def clean_iban(self):
        iban = self.cleaned_data["iban"].replace(" ", "").upper()
        if not iban.startswith("IR"):
            iban = "IR" + iban
        if not iban[2:].isdigit() or len(iban) != 26:
            raise forms.ValidationError("شماره شبا باید با IR و ۲۴ رقم باشد.")
        rearranged = iban[4:] + iban[:4]
        numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
        if int(numeric) % 97 != 1:
            raise forms.ValidationError("شماره شبا معتبر نیست.")
        return iban

    def clean(self):
        cleaned = super().clean()
        pw, confirm = cleaned.get("password"), cleaned.get("confirm_password")
        if pw and confirm and pw != confirm:
            self.add_error("confirm_password", "رمزهای واردشده یکسان نیستند.")
        return cleaned


class LoginForm(forms.Form):
    phone_number = forms.CharField(label="شماره موبایل")
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class TwoFAForm(forms.Form):
    token = forms.CharField(
        label="کد شش‌رقمی اپ احراز هویت",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )


class PhoneOTPForm(forms.Form):
    token = forms.CharField(
        label="کد یک‌بارمصرف پیامک‌شده", min_length=6, max_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )


class BankDetailsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("card_number", "iban")
        labels = {"card_number": "شماره کارت برای دریافت وام", "iban": "شماره شبا برای دریافت وام"}

    def clean_card_number(self):
        card = self.cleaned_data["card_number"].replace("-", "").replace(" ", "")
        if not card.isdigit() or len(card) != 16:
            raise forms.ValidationError("شماره کارت باید ۱۶ رقم باشد.")
        total = sum((int(digit) * (2 if index % 2 == 0 else 1)) - (9 if int(digit) * (2 if index % 2 == 0 else 1) > 9 else 0) for index, digit in enumerate(card))
        if total % 10:
            raise forms.ValidationError("شماره کارت معتبر نیست.")
        return card

    def clean_iban(self):
        iban = self.cleaned_data["iban"].replace(" ", "").upper()
        if not iban.startswith("IR"):
            iban = "IR" + iban
        if not iban[2:].isdigit() or len(iban) != 26:
            raise forms.ValidationError("شماره شبا باید با IR و ۲۴ رقم باشد.")
        numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in iban[4:] + iban[:4])
        if int(numeric) % 97 != 1:
            raise forms.ValidationError("شماره شبا معتبر نیست.")
        return iban
