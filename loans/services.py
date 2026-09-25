"""
منطق اصلی کسب‌وکار صندوق وام، جدا از admin.py و views.py تا هم قابل تست باشد
و هم بتوان همان منطق را هم از پنل مدیریت و هم از views فراخوانی کرد.
"""
import hashlib
import json
import secrets

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from .models import AuditLog, LotteryStatus, PaymentStatus, ReservationStatus


def log_action(actor, action, details=None, ip_address=None):
    """یک رویداد را در جدول AuditLog ثبت می‌کند (برای شفافیت و رسیدگی به اختلاف)."""
    AuditLog.objects.create(
        actor=actor if (actor is not None and getattr(actor, "is_authenticated", True)) else None,
        action=action,
        details=json.dumps(details, ensure_ascii=False) if details else "",
        ip_address=ip_address,
    )


@transaction.atomic
def start_loan_plan(plan):
    """
    یک طرح وام را از حالت باز/تکمیل‌شده به «در حال اجرا» می‌برد و برای همهٔ اعضای
    تأییدشده، ردیف‌های قسط (Payment) برای تمام دوره‌ها را می‌سازد.
    این عملیات را می‌توان چند بار صدا زد؛ اقساط تکراری ساخته نمی‌شوند (idempotent).
    """
    from .models import LoanPlan, Payment, PlanStatus  # جلوگیری از import چرخه‌ای

    plan = LoanPlan.objects.select_for_update().get(pk=plan.pk)
    if plan.status not in (PlanStatus.OPEN, PlanStatus.FULL, PlanStatus.IN_PROGRESS):
        raise ValueError("این وام در وضعیتی نیست که بتوان آن را شروع کرد.")

    confirmed = list(plan.reservations.filter(status=ReservationStatus.CONFIRMED))
    if not confirmed:
        raise ValueError("هیچ عضو تأییدشده‌ای برای شروع این طرح وجود ندارد.")

    if not plan.start_date:
        plan.start_date = timezone.localdate()
    plan.status = PlanStatus.IN_PROGRESS
    plan.save(update_fields=["start_date", "status"])

    for reservation in confirmed:
        for round_no in range(1, plan.duration_months + 1):
            due = plan.start_date + relativedelta(months=round_no - 1)
            # هزینهٔ خدمات صندوق یک‌بارمصرف است و به قسطِ دورهٔ اول اضافه می‌شود
            # تا واقعاً جمع‌آوری شود (نه فقط نمایشی بماند).
            amount = plan.monthly_payment + (plan.service_fee if round_no == 1 else 0)
            Payment.objects.get_or_create(
                reservation=reservation,
                round_number=round_no,
                defaults={"amount": amount, "due_date": due, "status": PaymentStatus.PENDING},
            )

    return plan


@transaction.atomic
def run_lottery_draw(draw, actor):
    """
    یک دور قرعه‌کشی را با تصادفی‌سازی امن (secrets، نه ماژول random) اجرا می‌کند.

    قوانین واجدشرایط‌بودن:
      ۱) رزرو باید «تأییدشده» باشد.
      ۲) عضو نباید پیش‌تر در همین طرح برنده شده باشد (تا وقتی همه یک نوبت نگرفته‌اند دوباره برنده نمی‌شود).
      ۳) قسط همین دوره باید «پرداخت‌شده» باشد.

    برای شفافیت، فهرست کامل واجدشرایط‌ها + یک اثرانگشت SHA-256 از (طرح، دوره، فهرست،
    برنده، زمان) ذخیره می‌شود تا در صورت اعتراض بتوان کل فرایند را رسیدگی کرد.
    """
    from .models import LoanPlan, LotteryDraw, Payment, PlanStatus, Reservation  # جلوگیری از import چرخه‌ای

    # همهٔ اجراهای یک طرح به‌ترتیب قفل می‌شوند؛ بنابراین دو مدیر نمی‌توانند برای
    # یک دوره هم‌زمان دو برندهٔ متفاوت ثبت کنند.
    plan_id = draw.loan_plan_id
    plan = LoanPlan.objects.select_for_update().get(pk=plan_id)
    draw = LotteryDraw.objects.select_for_update().get(pk=draw.pk)

    if draw.status != LotteryStatus.SCHEDULED:
        raise ValueError("این قرعه‌کشی قبلاً برگزار یا لغو شده است.")

    if plan.status != PlanStatus.IN_PROGRESS:
        raise ValueError("قرعه‌کشی فقط برای طرحِ در حال اجرا مجاز است.")
    if draw.round_number > plan.duration_months:
        raise ValueError("شمارهٔ دورهٔ قرعه‌کشی خارج از محدودهٔ طرح است.")
    if draw.scheduled_at > timezone.now():
        raise ValueError("زمان اعلام‌شدهٔ این قرعه‌کشی هنوز نرسیده است.")
    if LotteryDraw.objects.filter(
        loan_plan=plan, round_number__lt=draw.round_number, status=LotteryStatus.SCHEDULED
    ).exists():
        raise ValueError("ابتدا باید قرعه‌کشی دوره‌های پیشین برگزار یا لغو شوند.")

    reservations = Reservation.objects.select_for_update().filter(
        loan_plan=plan, status=ReservationStatus.CONFIRMED
    ).select_related("user")
    round_payments = {
        payment.reservation_id: payment
        for payment in Payment.objects.select_for_update().filter(
            reservation__loan_plan=plan, round_number=draw.round_number
        )
    }
    eligible = []
    for reservation in reservations:
        if reservation.has_won:
            continue
        payment = round_payments.get(reservation.id)
        if payment and payment.status == PaymentStatus.PAID:
            eligible.append(reservation)

    if not eligible:
        raise ValueError("هیچ عضو واجدشرایطی (با قسط پرداخت‌شدهٔ همین دوره) برای قرعه‌کشی یافت نشد.")

    # secrets.SystemRandom از CSPRNG سیستم‌عامل استفاده می‌کند — بر خلاف ماژول random
    # که برای مقاصد امنیتی/قرعه‌کشی مناسب نیست.
    rng = secrets.SystemRandom()
    winner = rng.choice(eligible)

    eligible_ids = sorted(r.id for r in eligible)
    snapshot = json.dumps(eligible_ids)
    now = timezone.now()
    fingerprint = hashlib.sha256(
        f"{draw.loan_plan_id}:{draw.round_number}:{snapshot}:{winner.id}:{now.isoformat()}".encode("utf-8")
    ).hexdigest()

    draw.eligible_snapshot = snapshot
    draw.winner_reservation = winner
    draw.status = LotteryStatus.COMPLETED
    draw.executed_at = now
    draw.integrity_hash = fingerprint
    draw.save()

    winner.has_won = True
    winner.won_round = draw.round_number
    winner.save(update_fields=["has_won", "won_round"])

    log_action(
        actor,
        "lottery_executed",
        {
            "plan_id": plan.id,
            "plan_title": plan.title,
            "round": draw.round_number,
            "winner_reservation_id": winner.id,
            "winner_user": str(winner.user),
            "eligible_count": len(eligible),
            "integrity_hash": fingerprint,
        },
    )

    return winner
