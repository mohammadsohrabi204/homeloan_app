"""تست‌های ثبت‌نام، ورود، محدودسازی نرخ و احراز هویت دومرحله‌ای."""
from unittest import mock

import pyotp
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import User
from .ratelimit import is_rate_limited


class RegistrationTests(TestCase):
    banking = {"card_number": "6037991199535182", "iban": "IR820540102680020817909002"}

    def test_successful_registration_creates_non_staff_user(self):
        self.client.post("/accounts/register/", {
            "full_name": "علی رضایی", "phone_number": "09121110001", "national_id": "",
            "password": "StrongPass!2026", "confirm_password": "StrongPass!2026",
        } | self.banking)
        user = User.objects.get(phone_number="09121110001")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_password_is_hashed_not_stored_in_plain_text(self):
        self.client.post("/accounts/register/", {
            "full_name": "علی رضایی", "phone_number": "09121110001", "national_id": "",
            "password": "StrongPass!2026", "confirm_password": "StrongPass!2026",
        } | self.banking)
        user = User.objects.get(phone_number="09121110001")
        self.assertNotEqual(user.password, "StrongPass!2026")
        self.assertTrue(user.check_password("StrongPass!2026"))

    def test_mismatched_passwords_rejected(self):
        self.client.post("/accounts/register/", {
            "full_name": "علی رضایی", "phone_number": "09121110001", "national_id": "",
            "password": "StrongPass!2026", "confirm_password": "DifferentPass!2026",
        } | self.banking)
        self.assertFalse(User.objects.filter(phone_number="09121110001").exists())

    def test_weak_password_rejected(self):
        self.client.post("/accounts/register/", {
            "full_name": "علی رضایی", "phone_number": "09121110001", "national_id": "",
            "password": "12345678", "confirm_password": "12345678",
        } | self.banking)
        self.assertFalse(User.objects.filter(phone_number="09121110001").exists())

    def test_invalid_phone_number_rejected(self):
        self.client.post("/accounts/register/", {
            "full_name": "علی رضایی", "phone_number": "12345", "national_id": "",
            "password": "StrongPass!2026", "confirm_password": "StrongPass!2026",
        } | self.banking)
        self.assertFalse(User.objects.filter(phone_number="12345").exists())

    def test_duplicate_phone_number_rejected(self):
        User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026"
        )
        self.client.post("/accounts/register/", {
            "full_name": "شخص دیگر", "phone_number": "09121110001", "national_id": "",
            "password": "StrongPass!2026", "confirm_password": "StrongPass!2026",
        } | self.banking)
        self.assertEqual(User.objects.filter(phone_number="09121110001").count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026", phone_verified=True
        )
        cache.clear()

    def test_login_with_correct_credentials(self):
        response = self.client.post("/accounts/login/", {
            "phone_number": "09121110001", "password": "StrongPass!2026",
        }, follow=True)
        self.assertEqual(response.request["PATH_INFO"], "/")

    def test_login_with_wrong_password_fails(self):
        response = self.client.post("/accounts/login/", {
            "phone_number": "09121110001", "password": "WrongPassword!",
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_dashboard_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        response = self.client.post("/accounts/logout/", follow=True)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class TwoFactorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026", phone_verified=True
        )
        cache.clear()

    def test_enable_2fa_then_login_requires_second_step(self):
        self.client.force_login(self.user)
        self.client.get("/accounts/2fa/setup/")
        secret = self.client.session["new_totp_secret"]
        self.client.post("/accounts/2fa/setup/", {"token": pyotp.TOTP(secret).now()})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_2fa_enabled)

        self.client.logout()
        response = self.client.post("/accounts/login/", {
            "phone_number": "09121110001", "password": "StrongPass!2026",
        }, follow=True)
        # رمز درست است ولی هنوز وارد نشده — منتظر کد دومرحله‌ای
        self.assertEqual(response.request["PATH_INFO"], "/accounts/login/2fa/")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        response = self.client.post(
            "/accounts/login/2fa/", {"token": pyotp.TOTP(secret).now()}, follow=True
        )
        self.assertEqual(response.request["PATH_INFO"], "/")

    def test_wrong_2fa_code_does_not_log_in(self):
        self.user.totp_secret = pyotp.random_base32()
        self.user.is_2fa_enabled = True
        self.user.save()

        self.client.post("/accounts/login/", {
            "phone_number": "09121110001", "password": "StrongPass!2026",
        })
        response = self.client.post("/accounts/login/2fa/", {"token": "000000"})
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_blocks_after_limit_reached(self):
        results = [is_rate_limited("unit-test", limit=3, window_seconds=60) for _ in range(5)]
        self.assertEqual(results, [False, False, False, True, True])

    def test_separate_keys_are_counted_separately(self):
        for _ in range(3):
            is_rate_limited("key-a", limit=3, window_seconds=60)
        self.assertFalse(is_rate_limited("key-b", limit=3, window_seconds=60))


class PhoneOTPTests(TestCase):
    """ورود دومرحله‌ایِ شمارهٔ موبایل (OTP پیامکی)"""

    def setUp(self):
        # شبیه‌سازی کاربر «نیمه‌ثبت‌نام‌شده»: حساب ساخته شده اما پیامک نرفته
        # (کاربر غیرفعال و شماره تأییدنشده)
        self.user = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026",
            phone_verified=False, is_active=False,
        )
        cache.clear()

    def test_otp_verification_is_rate_limited(self):
        self.user.phone_otp_hash = make_password("123456")
        self.user.phone_otp_expires_at = timezone.now() + timezone.timedelta(minutes=5)
        self.user.save(update_fields=["phone_otp_hash", "phone_otp_expires_at"])
        self.client.session["pending_phone_verification_user_id"] = self.user.id
        self.client.session.save()

        for _ in range(10):
            self.client.post("/accounts/verify-phone/", {"token": "000000"})

        # تلاش ۱۱ام مسدود می‌شود، حتی با کد درست — تا حدس‌زدن کد ۶ رقمی سخت شود
        self.client.post("/accounts/verify-phone/", {"token": "123456"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone_verified)

    def test_inactive_unverified_user_can_finish_registration_via_login(self):
        """اگر ارسال SMS در ثبت‌نام شکست بخورد، کاربر با ورود دوباره کد تازه می‌گیرد."""
        sent = {}
        with mock.patch(
            "accounts.views.send_phone_otp",
            side_effect=lambda phone, code: sent.update(code=code) or True,
        ):
            response = self.client.post("/accounts/login/", {
                "phone_number": "09121110001", "password": "StrongPass!2026",
            })
        self.assertRedirects(response, "/accounts/verify-phone/", status_code=302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        self.client.post("/accounts/verify-phone/", {"token": sent["code"]}, follow=True)
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)
        self.assertTrue(self.user.is_active)

    def test_deactivated_verified_user_cannot_login(self):
        User.objects.create_user(
            phone_number="09121110002", full_name="حساب غیرفعال", password="StrongPass!2026",
            phone_verified=True, is_active=False,
        )
        response = self.client.post("/accounts/login/", {
            "phone_number": "09121110002", "password": "StrongPass!2026",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class TwoFactorDisableTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026",
            phone_verified=True,
        )
        self.user.totp_secret = pyotp.random_base32()
        self.user.is_2fa_enabled = True
        self.user.save()
        cache.clear()

    def test_disable_2fa_with_valid_code(self):
        self.client.force_login(self.user)
        self.client.post("/accounts/2fa/disable/", {"token": pyotp.TOTP(self.user.totp_secret).now()})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_2fa_enabled)
        self.assertIsNone(self.user.totp_secret)

        # ورود بعدی دیگر مرحلهٔ دومرحله‌ای نمی‌خواهد
        self.client.logout()
        response = self.client.post("/accounts/login/", {
            "phone_number": "09121110001", "password": "StrongPass!2026",
        }, follow=True)
        self.assertEqual(response.request["PATH_INFO"], "/")

    def test_disable_2fa_rejects_wrong_code(self):
        self.client.force_login(self.user)
        self.client.post("/accounts/2fa/disable/", {"token": "000000"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_2fa_enabled)

    def test_disable_2fa_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/accounts/2fa/disable/").status_code, 405)
