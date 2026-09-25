from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import LoanPlan, PlanStatus, Reservation, ReservationStatus
from .services import log_action


@login_required
def dashboard(request):
    open_plans = (
        LoanPlan.objects.filter(status__in=[PlanStatus.OPEN, PlanStatus.FULL])
        .order_by("-created_at")
    )
    my_reservations = (
        request.user.reservations.filter(status=ReservationStatus.CONFIRMED)
        .select_related("loan_plan")
        .order_by("-reserved_at")
    )
    return render(
        request, "loans/dashboard.html",
        {"open_plans": open_plans, "my_reservations": my_reservations},
    )


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
    can_see_members = bool(my_reservation) or request.user.is_staff
    members_view = []
    if can_see_members:
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
            "can_see_members": can_see_members,
            "can_cancel": bool(my_reservation) and plan.status in (PlanStatus.OPEN, PlanStatus.FULL),
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

            # اگر این کاربر قبلاً رزروشده و آن را لغو کرده، همان ردیف را
            # دوباره فعال می‌کنیم (محدودیت یکتایی (کاربر، طرح) اجازهٔ ردیف دوم را نمی‌دهد).
            previous = locked_plan.reservations.filter(user=request.user, status=ReservationStatus.CANCELLED).first()
            if previous:
                previous.status = ReservationStatus.CONFIRMED
                previous.save(update_fields=["status"])
            else:
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


@login_required
def cancel_reservation(request, plan_id):
    """لغو رزرو توسط خود عضو — فقط تا پیش از شروع طرح (ساخت اقساط).

    پس از شروع، تعهد قسطی وجود دارد و لغو فقط با تصمیم مدیر ممکن است.
    """
    if request.method != "POST":
        return redirect("loans:plan_detail", plan_id=plan_id)

    plan = get_object_or_404(LoanPlan, pk=plan_id)

    with transaction.atomic():
        locked_plan = LoanPlan.objects.select_for_update().get(pk=plan.id)
        reservation = locked_plan.reservations.filter(
            user=request.user, status=ReservationStatus.CONFIRMED
        ).select_for_update().first()

        if not reservation:
            messages.info(request, "رزرو فعالی برای لغو وجود ندارد.")
            return redirect("loans:plan_detail", plan_id=plan.id)

        if locked_plan.status not in (PlanStatus.OPEN, PlanStatus.FULL):
            messages.warning(request, "طرح شروع شده است؛ دیگر امکان لغو رزرو از پنل کاربری نیست.")
            return redirect("loans:plan_detail", plan_id=plan.id)

        reservation.status = ReservationStatus.CANCELLED
        reservation.save(update_fields=["status"])

        # اگر طرح «تکمیل» بود و با لغو، جایی خالی شد، دوباره برای رزرو باز می‌شود.
        if locked_plan.status == PlanStatus.FULL and locked_plan.slots_left > 0:
            locked_plan.status = PlanStatus.OPEN
            locked_plan.save(update_fields=["status"])

    log_action(
        request.user, "reservation_cancelled",
        {"plan_id": plan.id, "reservation_id": reservation.id},
        request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, "رزرو شما لغو شد.")
    return redirect("loans:plan_detail", plan_id=plan.id)
