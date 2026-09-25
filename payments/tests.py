from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from loans.models import LoanPlan, Payment, PlanStatus, Reservation
from loans.services import start_loan_plan


class ManualReceiptTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="09120000000", full_name="مدیر", password="AdminPass!2026"
        )
        self.member = User.objects.create_user(
            phone_number="09121110001", full_name="عضو", password="StrongPass!2026"
        )
        plan = LoanPlan.objects.create(
            title="وام", total_amount=10_000_000, monthly_payment=1_000_000,
            duration_months=1, capacity=1, status=PlanStatus.OPEN, created_by=self.admin,
        )
        Reservation.objects.create(user=self.member, loan_plan=plan)
        start_loan_plan(plan)
        self.payment = Payment.objects.get(reservation__user=self.member)

    def test_member_can_submit_a_valid_manual_receipt(self):
        image_buffer = BytesIO()
        Image.new("RGB", (1, 1), color="white").save(image_buffer, format="PNG")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root, PAYMENT_GATEWAY="manual"):
            self.client.force_login(self.member)
            response = self.client.post(
                f"/payment/receipt/{self.payment.id}/",
                {"reference": "123456", "receipt": SimpleUploadedFile("receipt.png", image_buffer.getvalue(), content_type="image/png")},
            )

            self.assertEqual(response.status_code, 302)
            self.payment.refresh_from_db()
            self.assertEqual(self.payment.gateway, "manual")
            self.assertEqual(self.payment.manual_reference, "123456")
            self.assertTrue(self.payment.manual_receipt.name)
            self.assertIsNotNone(self.payment.receipt_submitted_at)

    def test_regular_member_cannot_view_receipt_file(self):
        self.client.force_login(self.member)
        response = self.client.get(f"/payment/receipt/{self.payment.id}/view/")
        self.assertEqual(response.status_code, 302)

    def test_new_receipt_clears_a_previous_rejection(self):
        self.payment.status = "receipt_rejected"
        self.payment.receipt_rejection_reason = "رسید واضح نیست"
        self.payment.save()
        image_buffer = BytesIO()
        Image.new("RGB", (1, 1), color="white").save(image_buffer, format="PNG")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root, PAYMENT_GATEWAY="manual"):
            self.client.force_login(self.member)
            self.client.post(
                f"/payment/receipt/{self.payment.id}/",
                {"reference": "654321", "receipt": SimpleUploadedFile("replacement.png", image_buffer.getvalue(), content_type="image/png")},
            )
            self.payment.refresh_from_db()
            self.assertEqual(self.payment.status, "pending")
            self.assertEqual(self.payment.receipt_rejection_reason, "")

    def test_staff_can_view_submitted_receipt(self):
        image_buffer = BytesIO()
        Image.new("RGB", (1, 1), color="white").save(image_buffer, format="PNG")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root, PAYMENT_GATEWAY="manual"):
            self.client.force_login(self.member)
            self.client.post(
                f"/payment/receipt/{self.payment.id}/",
                {"reference": "123456", "receipt": SimpleUploadedFile("receipt.png", image_buffer.getvalue(), content_type="image/png")},
            )
            self.client.force_login(self.admin)
            response = self.client.get(f"/payment/receipt/{self.payment.id}/view/")
            self.assertEqual(response.status_code, 200)
            response.close()

# Create your tests here.
