"""
ساخت دادهٔ نمونه برای نمایش/تست برنامه.

اجرا:
    python manage.py seed_demo

هشدار: این دستور کاربران نمونه با رمز عبور مشخص می‌سازد.
هرگز روی سرور واقعی اجرا نکنید — فقط برای نمایش و توسعه است.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from loans.models import LoanPlan, LotteryDraw, Payment, PaymentStatus, PlanStatus, Reservation
from loans.services import start_loan_plan

DEMO_PASSWORD = "Demo!Pass2026"

DEMO_MEMBERS = [
    ("09121110001", "علی رضایی"),
    ("09121110002", "زهرا احمدی"),
    ("09121110003", "محمد حسینی"),
    ("09121110004", "فاطمه موسوی"),
    ("09121110005", "رضا کریمی"),
]


class Command(BaseCommand):
    help = "ساخت دادهٔ نمونه (یک مدیر، پنج عضو و دو طرح وام) برای نمایش برنامه"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "این دستور فقط در حالت توسعه (DJANGO_DEBUG=true) قابل اجراست. "
                "روی سرور واقعی هرگز داده و رمز نمونه نسازید."
            )

        admin, created = User.objects.get_or_create(
            phone_number="09120000000",
            defaults={"full_name": "مدیر صندوق", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(DEMO_PASSWORD)
            admin.save()

        members = []
        for phone, name in DEMO_MEMBERS:
            user, was_created = User.objects.get_or_create(
                phone_number=phone, defaults={"full_name": name}
            )
            if was_created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            members.append(user)

        # طرح اول: باز برای رزرو
        open_plan, _ = LoanPlan.objects.get_or_create(
            title="وام خرید لوازم خانگی",
            defaults={
                "description": "صندوق قرض‌الحسنهٔ خانوادگی، بدون سود. هر ماه یک نفر به‌قید قرعه وام را دریافت می‌کند.",
                "total_amount": 60_000_000,
                "monthly_payment": 5_000_000,
                "duration_months": 12,
                "capacity": 12,
                "status": PlanStatus.OPEN,
                "created_by": admin,
            },
        )
        for user in members[:3]:
            Reservation.objects.get_or_create(user=user, loan_plan=open_plan)

        # طرح دوم: در حال اجرا، با اقساط و یک قرعه‌کشی زمان‌بندی‌شده
        running_plan, was_created = LoanPlan.objects.get_or_create(
            title="وام جهیزیه — دورهٔ بهار",
            defaults={
                "description": "طرح پنج‌نفره، پنج دوره. قرعه‌کشی هر ماه بین اعضایی که قسط همان ماه را پرداخت کرده‌اند.",
                "total_amount": 100_000_000,
                "monthly_payment": 20_000_000,
                "duration_months": 5,
                "capacity": 5,
                "status": PlanStatus.OPEN,
                "created_by": admin,
            },
        )
        if was_created:
            for user in members:
                Reservation.objects.get_or_create(user=user, loan_plan=running_plan)
            start_loan_plan(running_plan)

            # دو نفر قسط دورهٔ اول را پرداخت کرده‌اند
            Payment.objects.filter(
                reservation__loan_plan=running_plan,
                round_number=1,
                reservation__user__in=members[:2],
            ).update(status=PaymentStatus.PAID, paid_at=timezone.now(), gateway="manual")

            LotteryDraw.objects.get_or_create(
                loan_plan=running_plan,
                round_number=1,
                defaults={
                    "scheduled_at": timezone.now() + timezone.timedelta(days=3),
                    "created_by": admin,
                },
            )

        self.stdout.write(self.style.SUCCESS("\nدادهٔ نمونه ساخته شد.\n"))
        self.stdout.write("  مدیر :  09120000000")
        self.stdout.write("  عضو  :  09121110001 (و 09121110002 تا 09121110005)")
        self.stdout.write(f"  رمز همه :  {DEMO_PASSWORD}\n")
        self.stdout.write(self.style.WARNING("این رمزها فقط برای نمایش‌اند — روی سرور واقعی استفاده نکنید.\n"))
