"""تست‌های ثبت‌نام، ورود، محدودسازی نرخ و احراز هویت دومرحله‌ای."""
import pyotp
from django.core.cache import cache
from django.test import TestCase

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
