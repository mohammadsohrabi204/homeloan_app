"""
تست‌های خودکار منطق اصلی صندوق وام.
اجرا:  python manage.py test
"""
from datetime import date
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from payments.gateways import ManualGateway

from .models import (
    LoanPlan, LotteryDraw, LotteryStatus, Payment, PaymentStatus,
    PlanStatus, Reservation, ReservationStatus,
)
from .services import run_lottery_draw, start_loan_plan
from .jalali import format_jalali


class LoanLifecycleTests(TestCase):
    """چرخهٔ کامل: ساخت وام توسط مدیر → رزرو → شروع → پرداخت → قرعه‌کشی"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="09120000000", full_name="مدیر صندوق", password="AdminPass!2026"
        )
        self.member1 = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026"
        )
        self.member2 = User.objects.create_user(
            phone_number="09121110002", full_name="زهرا احمدی", password="StrongPass!2026"
        )
        self.plan = LoanPlan.objects.create(
            title="وام آزمایشی",
            total_amount=120_000_000,
            monthly_payment=10_000_000,
            duration_months=3,
            capacity=2,
            status=PlanStatus.OPEN,
            created_by=self.admin,
        )

    # --- رزرو ---------------------------------------------------------
    def test_member_can_reserve_open_plan(self):
        self.client.force_login(self.member1)
        self.client.post(f"/plans/{self.plan.id}/reserve/")
        self.assertEqual(self.plan.confirmed_count, 1)

    def test_duplicate_reservation_is_blocked(self):
        self.client.force_login(self.member1)
        self.client.post(f"/plans/{self.plan.id}/reserve/")
        self.client.post(f"/plans/{self.plan.id}/reserve/")
        self.assertEqual(
            Reservation.objects.filter(user=self.member1, loan_plan=self.plan).count(), 1
        )

    def test_reservation_beyond_capacity_is_rejected(self):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        Reservation.objects.create(user=self.member2, loan_plan=self.plan)
        self.plan.status = PlanStatus.FULL
        self.plan.save()

        member3 = User.objects.create_user(
            phone_number="09121110003", full_name="رضا کریمی", password="StrongPass!2026"
        )
        self.client.force_login(member3)
        self.client.post(f"/plans/{self.plan.id}/reserve/")
        self.assertEqual(self.plan.confirmed_count, 2)

    def test_anonymous_user_cannot_reserve(self):
        response = self.client.post(f"/plans/{self.plan.id}/reserve/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        self.assertEqual(self.plan.confirmed_count, 0)

    # --- شروع طرح و ساخت اقساط ---------------------------------------
    def test_start_plan_generates_installments_for_every_member(self):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        Reservation.objects.create(user=self.member2, loan_plan=self.plan)

        start_loan_plan(self.plan)
        self.plan.refresh_from_db()

        self.assertEqual(self.plan.status, PlanStatus.IN_PROGRESS)
        # ۲ عضو × ۳ دوره = ۶ قسط
        self.assertEqual(Payment.objects.filter(reservation__loan_plan=self.plan).count(), 6)

    def test_start_plan_twice_does_not_duplicate_installments(self):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        start_loan_plan(self.plan)
        self.plan.status = PlanStatus.OPEN  # شبیه‌سازی اجرای دوبارهٔ تصادفی
        self.plan.save()
        start_loan_plan(self.plan)
        self.assertEqual(Payment.objects.filter(reservation__loan_plan=self.plan).count(), 3)

    def test_start_plan_without_members_raises(self):
        with self.assertRaises(ValueError):
            start_loan_plan(self.plan)

    # --- قرعه‌کشی ------------------------------------------------------
    def _prepare_paid_round(self, round_number=1):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        Reservation.objects.create(user=self.member2, loan_plan=self.plan)
        start_loan_plan(self.plan)
        Payment.objects.filter(round_number=round_number).update(
            status=PaymentStatus.PAID, paid_at=timezone.now()
        )
        return LotteryDraw.objects.create(
            loan_plan=self.plan,
            round_number=round_number,
            scheduled_at=timezone.now(),
            created_by=self.admin,
        )

    def test_lottery_picks_a_winner_and_records_proof(self):
        draw = self._prepare_paid_round()
        winner = run_lottery_draw(draw, actor=self.admin)
        draw.refresh_from_db()

        self.assertEqual(draw.status, LotteryStatus.COMPLETED)
        self.assertEqual(draw.winner_reservation_id, winner.id)
        self.assertTrue(draw.integrity_hash)
        self.assertEqual(len(draw.eligible_ids()), 2)

    def test_unpaid_member_is_excluded_from_lottery(self):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        res2 = Reservation.objects.create(user=self.member2, loan_plan=self.plan)
        start_loan_plan(self.plan)

        # فقط عضو اول قسط دورهٔ ۱ را پرداخت کرده است
        Payment.objects.filter(reservation__user=self.member1, round_number=1).update(
            status=PaymentStatus.PAID, paid_at=timezone.now()
        )
        draw = LotteryDraw.objects.create(
            loan_plan=self.plan, round_number=1, scheduled_at=timezone.now(), created_by=self.admin
        )
        winner = run_lottery_draw(draw, actor=self.admin)

        self.assertEqual(winner.user, self.member1)
        self.assertNotIn(res2.id, draw.eligible_ids())

    def test_previous_winner_cannot_win_twice(self):
        draw1 = self._prepare_paid_round(round_number=1)
        first_winner = run_lottery_draw(draw1, actor=self.admin)

        Payment.objects.filter(round_number=2).update(
            status=PaymentStatus.PAID, paid_at=timezone.now()
        )
        draw2 = LotteryDraw.objects.create(
            loan_plan=self.plan, round_number=2, scheduled_at=timezone.now(), created_by=self.admin
        )
        second_winner = run_lottery_draw(draw2, actor=self.admin)

        self.assertNotEqual(first_winner.id, second_winner.id)

    def test_completed_draw_cannot_run_again(self):
        draw = self._prepare_paid_round()
        run_lottery_draw(draw, actor=self.admin)
        with self.assertRaises(ValueError):
            run_lottery_draw(draw, actor=self.admin)

    def test_lottery_without_eligible_members_raises(self):
        Reservation.objects.create(user=self.member1, loan_plan=self.plan)
        start_loan_plan(self.plan)  # هیچ قسطی پرداخت نشده
        draw = LotteryDraw.objects.create(
            loan_plan=self.plan, round_number=1, scheduled_at=timezone.now(), created_by=self.admin
        )
        with self.assertRaises(ValueError):
            run_lottery_draw(draw, actor=self.admin)

    def test_lottery_cannot_run_before_scheduled_time(self):
        draw = self._prepare_paid_round()
        draw.scheduled_at = timezone.now() + timezone.timedelta(minutes=1)
        draw.save(update_fields=["scheduled_at"])

        with self.assertRaises(ValueError):
            run_lottery_draw(draw, actor=self.admin)

    def test_later_lottery_cannot_run_before_previous_round(self):
        self._prepare_paid_round(round_number=1)
        Payment.objects.filter(round_number=2).update(status=PaymentStatus.PAID, paid_at=timezone.now())
        later_draw = LotteryDraw.objects.create(
            loan_plan=self.plan, round_number=2, scheduled_at=timezone.now(), created_by=self.admin
        )

        with self.assertRaises(ValueError):
            run_lottery_draw(later_draw, actor=self.admin)

    def test_database_rejects_invalid_financial_values(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LoanPlan.objects.create(
                title="طرح نامعتبر", total_amount=0, monthly_payment=0,
                duration_months=0, capacity=0, created_by=self.admin,
            )


class PrivacyAndPermissionTests(TestCase):
    """چه کسی چه چیزی را می‌بیند و چه کسی اجازهٔ چه کاری دارد"""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="09120000000", full_name="مدیر صندوق", password="AdminPass!2026"
        )
        self.member = User.objects.create_user(
            phone_number="09121110001", full_name="علی رضایی", password="StrongPass!2026"
        )
        self.outsider = User.objects.create_user(
            phone_number="09121110009", full_name="کاربر غریبه", password="StrongPass!2026"
        )
        self.plan = LoanPlan.objects.create(
            title="وام آزمایشی", total_amount=120_000_000, monthly_payment=10_000_000,
            duration_months=3, capacity=5, status=PlanStatus.OPEN, created_by=self.admin,
        )
        Reservation.objects.create(user=self.member, loan_plan=self.plan)

    def test_non_member_cannot_see_member_list(self):
        self.client.force_login(self.outsider)
        response = self.client.get(f"/plans/{self.plan.id}/")
        self.assertNotContains(response, "علی رضایی")

    def test_member_can_see_member_list(self):
        self.client.force_login(self.member)
        response = self.client.get(f"/plans/{self.plan.id}/")
        self.assertContains(response, "علی رضایی")

    def test_regular_member_cannot_access_admin_panel(self):
        self.client.force_login(self.member)
        response = self.client.get("/admin/", follow=True)
        self.assertIn("login", response.request["PATH_INFO"])

    def test_admin_can_access_admin_panel(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_user_cannot_pay_someone_elses_installment(self):
        start_loan_plan(self.plan)
        other_payment = Payment.objects.filter(reservation__user=self.member).first()

        self.client.force_login(self.outsider)
        response = self.client.post(f"/payment/pay/{other_payment.id}/")
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_confirm_payment_via_callback_of_another_user(self):
        start_loan_plan(self.plan)
        other_payment = Payment.objects.filter(reservation__user=self.member).first()

        self.client.force_login(self.outsider)
        response = self.client.get(f"/payment/callback/{other_payment.id}/?Authority=x&Status=OK")
        self.assertEqual(response.status_code, 403)
        other_payment.refresh_from_db()
        self.assertEqual(other_payment.status, PaymentStatus.PENDING)

    def test_callback_rejects_an_authority_from_another_payment(self):
        start_loan_plan(self.plan)
        payment = Payment.objects.filter(reservation__user=self.member).first()
        payment.gateway_authority = "authority-for-a-different-payment"
        payment.save(update_fields=["gateway_authority"])

        self.client.force_login(self.member)
        response = self.client.get(
            f"/payment/callback/{payment.id}/?Authority=tampered-authority&Status=OK"
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_payment_start_requires_post(self):
        start_loan_plan(self.plan)
        payment = Payment.objects.filter(reservation__user=self.member).first()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(f"/payment/pay/{payment.id}/").status_code, 405)


class PaymentGatewayTests(TestCase):
    """درگاه دستی نباید خودش پرداخت را تأیید کند"""

    def test_manual_gateway_never_auto_verifies(self):
        gateway = ManualGateway()
        result = gateway.verify_payment(amount=10_000_000, authority="abc")
        self.assertFalse(result["ok"])

    def test_manual_gateway_returns_callback_url(self):
        gateway = ManualGateway()
        result = gateway.request_payment(
            amount=10_000_000, description="تست", callback_url="https://example.com/cb"
        )
        self.assertIn("authority", result)
        self.assertTrue(result["redirect_url"].startswith("https://example.com/cb"))


class JalaliDateTests(TestCase):
    def test_gregorian_date_is_displayed_as_jalali(self):
        self.assertEqual(format_jalali(date(2026, 9, 17)), "۱۴۰۵/۰۶/۲۶")
