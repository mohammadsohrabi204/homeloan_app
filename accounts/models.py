from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r"^09\d{9}$",
    message="شماره موبایل باید به‌صورت ۰۹xxxxxxxxx و ۱۱ رقمی باشد.",
)


class UserManager(BaseUserManager):
    """
    مدیر کاربر سفارشی: به‌جای username از phone_number به‌عنوان شناسهٔ ورود استفاده می‌شود.
    """

    use_in_migrations = True

    def _create_user(self, phone_number, full_name, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("شماره موبایل الزامی است.")
        phone_number = phone_number.strip()
        user = self.model(phone_number=phone_number, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone_number, full_name, password, **extra_fields)

    def create_superuser(self, phone_number, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("کاربر مدیر باید is_staff=True داشته باشد.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("کاربر مدیر باید is_superuser=True داشته باشد.")
        return self._create_user(phone_number, full_name, password, **extra_fields)


class User(AbstractUser):
    """
    کاربر برنامه. is_staff = مدیرِ صندوق وام (دسترسی به پنل مدیریت و ساخت طرح‌های وام).
    بقیهٔ کاربران فقط عضو عادی هستند: فقط می‌توانند رزرو کنند و قسط پرداخت کنند.
    """

    username = None
    first_name = None
    last_name = None

    full_name = models.CharField("نام و نام خانوادگی", max_length=120)
    phone_number = models.CharField(
        "شماره موبایل", max_length=11, unique=True, validators=[phone_validator]
    )
    national_id = models.CharField(
        "کد ملی", max_length=10, unique=True, null=True, blank=True
    )
    card_number = models.CharField("شماره کارت برای دریافت وام", max_length=16, blank=True)
    iban = models.CharField("شماره شبای برای دریافت وام", max_length=26, blank=True)
    phone_verified = models.BooleanField("شماره موبایل تأیید شده", default=False)
    phone_otp_hash = models.CharField(max_length=128, blank=True)
    phone_otp_expires_at = models.DateTimeField(null=True, blank=True)

    # احراز هویت دو مرحله‌ای (TOTP) — کاملاً اختیاری اما به‌شدت برای حساب مدیر توصیه می‌شود
    totp_secret = models.CharField(max_length=64, null=True, blank=True)
    is_2fa_enabled = models.BooleanField("۲مرحله‌ای فعال است", default=False)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"
