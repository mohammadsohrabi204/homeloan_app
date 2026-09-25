import base64
import io
import secrets

import pyotp
import qrcode
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from loans.services import log_action

from .forms import BankDetailsForm, LoginForm, PhoneOTPForm, RegisterForm, TwoFAForm
from .models import User
from .ratelimit import is_rate_limited
from .sms import send_phone_otp


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def _send_phone_otp(request, user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.phone_otp_hash = make_password(code)
    user.phone_otp_expires_at = timezone.now() + timezone.timedelta(minutes=settings.PHONE_OTP_TTL_MINUTES)
    user.save(update_fields=["phone_otp_hash", "phone_otp_expires_at"])
    if not send_phone_otp(user.phone_number, code):
        return False
    request.session["pending_phone_verification_user_id"] = user.id
    return True


def register_view(request):
    if request.user.is_authenticated:
        return redirect("loans:dashboard")

    ip = _client_ip(request)
    if is_rate_limited(f"register:{ip}", limit=10, window_seconds=3600):
        messages.error(request, "تعداد درخواست‌های ثبت‌نام از این آدرس بیش از حد مجاز است. کمی بعد دوباره تلاش کنید.")
        return render(request, "accounts/register.html", {"form": RegisterForm()})

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                phone_number=form.cleaned_data["phone_number"],
                full_name=form.cleaned_data["full_name"].strip(),
                national_id=form.cleaned_data.get("national_id"),
                card_number=form.cleaned_data["card_number"],
                iban=form.cleaned_data["iban"],
                password=form.cleaned_data["password"],
                is_active=False,
            )
            log_action(user, "user_registered", ip_address=ip)
            if _send_phone_otp(request, user):
                messages.success(request, "کد تأیید به شمارهٔ موبایل شما ارسال شد.")
                return redirect("accounts:verify_phone")
            messages.error(request, "ارسال کد تأیید ناموفق بود. تنظیمات سرویس پیامک را بررسی کنید.")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def verify_phone_view(request):
    user_id = request.session.get("pending_phone_verification_user_id")
    user = User.objects.filter(pk=user_id, phone_verified=False).first()
    if not user:
        return redirect("accounts:register")
    form = PhoneOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # محدودسازی تلاش‌های واردکردن کد: کد پیامکی ۶ رقمی است و بدون سقف،
        # حدس‌زدن آن در پنجرهٔ اعتبار (۵ دقیقه) ممکن می‌شود.
        if is_rate_limited(f"phone-otp-verify:{user.id}", limit=10, window_seconds=300):
            messages.error(request, "تلاش‌های واردکردن کد بیش از حد مجاز است. برای دریافت کد جدید، دکمهٔ ارسال مجدد را بزنید.")
            return render(request, "accounts/verify_phone.html", {"form": form, "phone": user.phone_number})
        expired = not user.phone_otp_expires_at or user.phone_otp_expires_at < timezone.now()
        if not expired and check_password(form.cleaned_data["token"], user.phone_otp_hash):
            user.phone_verified = True
            user.is_active = True
            user.phone_otp_hash = ""
            user.phone_otp_expires_at = None
            user.save(update_fields=["phone_verified", "is_active", "phone_otp_hash", "phone_otp_expires_at"])
            request.session.pop("pending_phone_verification_user_id", None)
            log_action(user, "phone_verified", ip_address=_client_ip(request))
            messages.success(request, "شماره موبایل تأیید شد؛ اکنون وارد شوید.")
            return redirect("accounts:login")
        messages.error(request, "کد نادرست است یا اعتبار آن تمام شده است.")
    return render(request, "accounts/verify_phone.html", {"form": form, "phone": user.phone_number})


@require_POST
def resend_phone_otp_view(request):
    user_id = request.session.get("pending_phone_verification_user_id")
    user = User.objects.filter(pk=user_id, phone_verified=False).first()
    if not user:
        return redirect("accounts:register")
    if is_rate_limited(f"phone-otp:{user.id}", limit=3, window_seconds=600):
        messages.error(request, "درخواست کد بیش از حد مجاز است. چند دقیقه بعد دوباره تلاش کنید.")
    elif _send_phone_otp(request, user):
        messages.success(request, "کد جدید ارسال شد.")
    else:
        messages.error(request, "ارسال کد ناموفق بود.")
    return redirect("accounts:verify_phone")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("loans:dashboard")

    ip = _client_ip(request)
    form = LoginForm(request.POST or None)

    if request.method == "POST":
        if is_rate_limited(f"login:{ip}", limit=15, window_seconds=60):
            messages.error(request, "تعداد تلاش‌های ورود بیش از حد مجاز است. کمی صبر کنید و دوباره امتحان کنید.")
            return render(request, "accounts/login.html", {"form": form})

        if form.is_valid():
            phone = form.cleaned_data["phone_number"].strip()
            password = form.cleaned_data["password"]
            user = authenticate(request, username=phone, password=password)

            if user is None:
                # authenticate() برای کاربران «غیرفعال» هم None برمی‌گرداند. کاربر
                # نیمه‌ثبت‌نام‌شده (در زمان ثبت‌نام ساخته شده اما ارسال پیامک شکست
                # خورده و هنوز غیرفعال است) باید بتواند با کد تازه، ثبت‌نام را به‌جا
                # بیاورد؛ بنابراین چنین کاربری را مستقیماً بررسی می‌کنیم.
                candidate = User.objects.filter(phone_number=phone).first()
                if candidate is not None and not candidate.phone_verified and check_password(password, candidate.password):
                    if _send_phone_otp(request, candidate):
                        messages.info(request, "برای ورود، ابتدا شماره موبایل خود را با کد پیامک‌شده تأیید کنید.")
                        return redirect("accounts:verify_phone")
                    messages.error(request, "ارسال کد تأیید ناموفق بود. تنظیمات سرویس پیامک را بررسی کنید.")
                    return render(request, "accounts/login.html", {"form": form})

                # در تمام مسایر ناموفق، یک هش اضافه (واقعی یا خال) اجرا می‌کنیم تا
                # زمان پاسخ برای «کاربر یافت‌نشده»، «رمز اشتباه» و «حساب غیرفعال»
                # یکسان بماند و وجود حساب از زمان پاسخ لو نرود.
                if candidate is None or candidate.phone_verified:
                    User().set_password(password)

                messages.error(request, "شماره موبایل یا رمز عبور اشتباه است.")
                log_action(None, "login_failed", {"phone": phone}, ip)
                return render(request, "accounts/login.html", {"form": form})

            if not user.phone_verified:
                # کاربر «نیمه‌ثبت‌نام‌شده»: کاربر در زمان ثبت‌نام ساخته شده اما
                # ارسال کد پیامکی ناموفق بوده و حساب هنوز غیرفعال است. با ارسال
                # کد جدید اینجا، او می‌تواند ثبت‌نام را به‌جا بیاورد و یک خطای
                # گذرای پیامک باعث غیرقابل‌استفاده‌شدن دائمی حساب نمی‌شود.
                if _send_phone_otp(request, user):
                    messages.info(request, "برای ورود، ابتدا شماره موبایل خود را با کد پیامک‌شده تأیید کنید.")
                    return redirect("accounts:verify_phone")
                messages.error(request, "ارسال کد تأیید ناموفق بود. تنظیمات سرویس پیامک را بررسی کنید.")
                return render(request, "accounts/login.html", {"form": form})

            if not user.is_active:
                # حسابی که (مثلاً توسط مدیر) غیرفعال شده — همان رفتار قبلی:
                # پیام مبهم تا وجود/غیرفعال‌بودن حساب لو نرود.
                messages.error(request, "شماره موبایل یا رمز عبور اشتباه است.")
                log_action(None, "login_failed", {"phone": phone}, ip)
                return render(request, "accounts/login.html", {"form": form})

            if user.is_2fa_enabled:
                request.session["pending_2fa_user_id"] = user.id
                return redirect("accounts:verify_2fa")

            auth_login(request, user)
            log_action(user, "login_success", ip_address=ip)
            return redirect("loans:dashboard")

    return render(request, "accounts/login.html", {"form": form})


def verify_2fa_view(request):
    user_id = request.session.get("pending_2fa_user_id")
    if not user_id:
        return redirect("accounts:login")

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        request.session.pop("pending_2fa_user_id", None)
        return redirect("accounts:login")

    ip = _client_ip(request)
    form = TwoFAForm(request.POST or None)

    if request.method == "POST":
        if is_rate_limited(f"2fa:{ip}:{user.id}", limit=10, window_seconds=60):
            messages.error(request, "تعداد تلاش‌های واردکردن کد بیش از حد مجاز است.")
            return render(request, "accounts/verify_2fa.html", {"form": form})

        if form.is_valid():
            totp = pyotp.TOTP(user.totp_secret)
            if totp.verify(form.cleaned_data["token"], valid_window=1):
                request.session.pop("pending_2fa_user_id", None)
                auth_login(request, user)
                log_action(user, "login_success_2fa", ip_address=ip)
                return redirect("loans:dashboard")
            messages.error(request, "کد وارد شده صحیح نیست.")
            log_action(user, "login_2fa_failed", ip_address=ip)

    return render(request, "accounts/verify_2fa.html", {"form": form})


@login_required
@require_POST
def logout_view(request):
    log_action(request.user, "logout", ip_address=_client_ip(request))
    auth_logout(request)
    messages.info(request, "با موفقیت از حساب کاربری خارج شدید.")
    return redirect("accounts:login")


@login_required
def setup_2fa_view(request):
    if request.user.is_2fa_enabled:
        messages.info(request, "احراز هویت دو مرحله‌ای از قبل برای حساب شما فعال است.")
        return redirect("accounts:account")

    if "new_totp_secret" not in request.session:
        request.session["new_totp_secret"] = pyotp.random_base32()
    secret = request.session["new_totp_secret"]

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=request.user.phone_number, issuer_name="صندوق وام خانگی")
    qr_img = qrcode.make(uri)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("ascii")

    form = TwoFAForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        totp = pyotp.TOTP(secret)
        if totp.verify(form.cleaned_data["token"], valid_window=1):
            request.user.totp_secret = secret
            request.user.is_2fa_enabled = True
            request.user.save(update_fields=["totp_secret", "is_2fa_enabled"])
            request.session.pop("new_totp_secret", None)
            log_action(request.user, "2fa_enabled", ip_address=_client_ip(request))
            messages.success(request, "احراز هویت دو مرحله‌ای با موفقیت فعال شد.")
            return redirect("accounts:account")
        messages.error(request, "کد وارد شده صحیح نیست.")

    return render(
        request,
        "accounts/setup_2fa.html",
        {"form": form, "qr_base64": qr_base64, "secret": secret},
    )


@login_required
@require_POST
def disable_2fa_view(request):
    """غیرفعال‌کردن ۲FA فقط با کد معتبر اپ احراز هویت — تا حساب از روی دستگاه
    غیرمعتبرِ کسی که اپ را ندارد باز نشود."""
    if not request.user.is_2fa_enabled:
        return redirect("accounts:account")

    form = TwoFAForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        totp = pyotp.TOTP(request.user.totp_secret or "")
        if totp.verify(form.cleaned_data["token"], valid_window=1):
            request.user.totp_secret = None
            request.user.is_2fa_enabled = False
            request.user.save(update_fields=["totp_secret", "is_2fa_enabled"])
            log_action(request.user, "2fa_disabled", ip_address=_client_ip(request))
            messages.success(request, "احراز هویت دو مرحله‌ای غیرفعال شد.")
        else:
            messages.error(request, "کد وارد شده صحیح نیست؛ ۲FA هنوز فعال است.")

    return redirect("accounts:account")


@login_required
def account_view(request):
    form = BankDetailsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_action(request.user, "bank_details_updated", ip_address=_client_ip(request))
        messages.success(request, "اطلاعات بانکی شما ذخیره شد.")
        return redirect("accounts:account")
    return render(request, "accounts/account.html", {"bank_form": form})
