from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone

from .models import LoanPlan, Notification, Payment, PaymentStatus, PlanStatus, Reservation, ReservationStatus
from .services import log_action, notify_upcoming_and_overdue_payments


@login_required
def dashboard(request):
    notify_upcoming_and_overdue_payments()
    open_plans = (
        LoanPlan.objects.filter(status__in=[PlanStatus.OPEN, PlanStatus.FULL])
        .order_by("-created_at")
    )
    my_reservations = (
        request.user.reservations.filter(status=ReservationStatus.CONFIRMED)
        .select_related("loan_plan")
        .annotate(
            total_installments=Count("payments"),
            paid_installments=Count(
                "payments",
                filter=Q(payments__status=PaymentStatus.PAID),
            ),
        )
        .order_by("-reserved_at")
    )

    next_payment = (
        Payment.objects.filter(
            reservation__user=request.user,
            reservation__status=ReservationStatus.CONFIRMED,
        )
        .exclude(status=PaymentStatus.PAID)
        .select_related("reservation__loan_plan")
        .order_by("due_date", "round_number")
        .first()
    )
    unpaid_count = (
        Payment.objects.filter(
            reservation__user=request.user,
            reservation__status=ReservationStatus.CONFIRMED,
        )
        .exclude(status=PaymentStatus.PAID)
        .count()
    )

    return render(
        request,
        "loans/dashboard.html",
        {
            "open_plans": open_plans,
            "my_reservations": my_reservations,
            "active_loan_count": my_reservations.count(),
            "unpaid_count": unpaid_count,
            "next_payment": next_payment,
        },
    )



def staff_required(view_func):
    return user_passes_test(lambda user: user.is_staff, login_url="accounts:login")(view_func)


@staff_required
def manager_dashboard(request):
    now = timezone.now()
    plans = LoanPlan.objects.all().order_by("-created_at")
    selected_plan = request.GET.get("plan", "").strip()
    status_filter = request.GET.get("status", "").strip()
    search = request.GET.get("q", "").strip()

    payments_qs = Payment.objects.filter(
        reservation__status=ReservationStatus.CONFIRMED
    ).select_related("reservation__user", "reservation__loan_plan")

    if selected_plan.isdigit():
        payments_qs = payments_qs.filter(reservation__loan_plan_id=int(selected_plan))
    if search:
        payments_qs = payments_qs.filter(
            Q(reservation__user__full_name__icontains=search)
            | Q(reservation__user__phone_number__icontains=search)
        )

    payments = payments_qs.order_by("-receipt_submitted_at", "due_date", "round_number")
    payment_rows = []
    for payment in payments:
        is_overdue = payment.status != PaymentStatus.PAID and payment.due_date and payment.due_date < timezone.localdate()
        has_receipt = bool(payment.manual_receipt)
        is_new_receipt = has_receipt and payment.status != PaymentStatus.PAID
        if status_filter == "overdue" and not is_overdue:
            continue
        if status_filter == "receipts" and not is_new_receipt:
            continue
        payment_rows.append({
            "payment": payment,
            "is_overdue": is_overdue,
            "has_receipt": has_receipt,
            "is_new_receipt": is_new_receipt,
        })

    total_members = Reservation.objects.filter(status=ReservationStatus.CONFIRMED).values("user_id").distinct().count()
    total_paid = Payment.objects.filter(status=PaymentStatus.PAID).count()
    pending_receipts = Payment.objects.exclude(manual_receipt="").exclude(status=PaymentStatus.PAID).count()
    overdue_count = Payment.objects.filter(due_date__lt=timezone.localdate()).exclude(status=PaymentStatus.PAID).count()

    return render(
        request,
        "loans/manager_dashboard.html",
        {
            "plans": plans,
            "payment_rows": payment_rows,
            "total_members": total_members,
            "total_paid": total_paid,
            "pending_receipts": pending_receipts,
            "overdue_count": overdue_count,
            "selected_plan": selected_plan,
            "status_filter": status_filter,
            "search": search,
        },
    )


@staff_required
@require_POST
def manager_payment_action(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related("reservation__loan_plan", "reservation__user"),
        pk=payment_id,
    )
    action = request.POST.get("action")
    if payment.status == PaymentStatus.PAID:
        messages.info(request, "این قسط قبلاً تأیید شده است.")
        return redirect("loans:manager_dashboard")

    if action == "approve":
        payment.status = PaymentStatus.PAID
        payment.paid_at = timezone.now()
        payment.confirmed_by = request.user
        payment.receipt_rejection_reason = ""
        payment.save(update_fields=["status", "paid_at", "confirmed_by", "receipt_rejection_reason"])
        Notification.objects.create(user=payment.reservation.user, title="تأیید پرداخت", message=f"پرداخت قسط دورهٔ {payment.round_number} وام «{payment.reservation.loan_plan.title}» تأیید شد.")
        log_action(request.user, "manual_payment_approved", {"payment_id": payment.id}, request.META.get("REMOTE_ADDR"))
        messages.success(request, "پرداخت با موفقیت تأیید شد.")
    elif action == "reject":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "برای رد رسید باید دلیل وارد شود.")
            return redirect("loans:manager_dashboard")
        payment.status = PaymentStatus.RECEIPT_REJECTED
        payment.receipt_rejection_reason = reason[:500]
        payment.save(update_fields=["status", "receipt_rejection_reason"])
        Notification.objects.create(user=payment.reservation.user, title="رد رسید پرداخت", message=f"رسید قسط دورهٔ {payment.round_number} وام «{payment.reservation.loan_plan.title}» رد شد. دلیل: {reason[:500]}")
        log_action(
            request.user,
            "manual_receipt_rejected",
            {"payment_id": payment.id, "reason": reason[:500]},
            request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "رسید رد شد و دلیل آن ثبت گردید.")
    else:
        messages.error(request, "عملیات نامعتبر است.")
    return redirect("loans:manager_dashboard")



@login_required
def notifications(request):
    items = request.user.notifications.all()[:50]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "loans/notifications.html", {"notifications": items})


@login_required
def plan_detail(request, plan_id):
    plan = get_object_or_404(LoanPlan, pk=plan_id)

    my_reservation = (
        Reservation.objects.filter(user=request.user, loan_plan=plan)
        .exclude(status=ReservationStatus.CANCELLED)
        .first()
    )

    # فقط اعضای همان طرح (یا مدیر) فهرست کامل اعضا و وضعیت پرداختشان را می‌بینند —
    # کاربرانی که هنوز عضو نشده‌اند فقط آمار کلی (ظرفیت/باقی‌مانده) را می‌بینند.
    members_view = []
    if my_reservation or request.user.is_staff:
        for r in plan.reservations.filter(status=ReservationStatus.CONFIRMED).select_related("user"):
            members_view.append(
                {
                    "name": r.user.full_name,
                    "has_won": r.has_won,
                    "won_round": r.won_round,
                    "is_me": r.user_id == request.user.id,
                }
            )

    my_payments = my_reservation.payments.order_by("round_number") if my_reservation else []
    draws = plan.lottery_draws.order_by("round_number").select_related("winner_reservation__user")

    return render(
        request,
        "loans/plan_detail.html",
        {
            "plan": plan,
            "my_reservation": my_reservation,
            "members_view": members_view,
            "my_payments": my_payments,
            "draws": draws,
            "manual_gateway": settings.PAYMENT_GATEWAY in ("manual", "both"),
            "online_gateway": settings.PAYMENT_GATEWAY in ("zarinpal", "both"),
        },
    )


@login_required
def reserve(request, plan_id):
    plan = get_object_or_404(LoanPlan, pk=plan_id)

    if request.method != "POST":
        return redirect("loans:plan_detail", plan_id=plan.id)

    if plan.status != PlanStatus.OPEN:
        messages.warning(request, "این وام دیگر برای رزرو باز نیست.")
        return redirect("loans:plan_detail", plan_id=plan.id)

    try:
        with transaction.atomic():
            # select_for_update ردیف طرح را در دیتابیس قفل می‌کند تا در صورت رزرو
            # هم‌زمان چند نفر، ظرفیت هرگز از حد مجاز عبور نکند (PostgreSQL/MySQL).
            # نکته: SQLite قفل ردیفی واقعی ندارد؛ برای استفادهٔ همزمانِ واقعی از PostgreSQL استفاده کنید.
            locked_plan = LoanPlan.objects.select_for_update().get(pk=plan.id)
            if locked_plan.status != PlanStatus.OPEN or locked_plan.slots_left <= 0:
                messages.warning(request, "ظرفیت این وام تکمیل شده است.")
                return redirect("loans:plan_detail", plan_id=plan.id)

            Reservation.objects.create(
                user=request.user, loan_plan=locked_plan, status=ReservationStatus.CONFIRMED
            )

            if locked_plan.slots_left <= 0:
                locked_plan.status = PlanStatus.FULL
                locked_plan.save(update_fields=["status"])
    except IntegrityError:
        messages.info(request, "شما قبلاً در این وام ثبت‌نام کرده‌اید.")
        return redirect("loans:plan_detail", plan_id=plan.id)

    log_action(request.user, "reservation_created", {"plan_id": plan.id}, request.META.get("REMOTE_ADDR"))
    messages.success(request, "رزرو شما با موفقیت ثبت شد.")
    return redirect("loans:plan_detail", plan_id=plan.id)
