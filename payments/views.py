from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
import mimetypes

from loans.models import Payment, PaymentStatus
from loans.services import log_action

from .gateways import PaymentError, get_gateway
from .forms import ManualReceiptForm


@login_required
@require_POST
def pay(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.reservation.user_id != request.user.id:
        raise PermissionDenied

    if payment.status == PaymentStatus.PAID:
        messages.info(request, "این قسط قبلاً پرداخت شده است.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    configured_gateway = settings.PAYMENT_GATEWAY
    selected_method = request.POST.get("payment_method")
    if configured_gateway == "both":
        if selected_method != "zarinpal":
            raise PermissionDenied
        gateway = get_gateway("zarinpal")
    elif configured_gateway == "zarinpal":
        gateway = get_gateway("zarinpal")
    else:
        gateway = get_gateway("manual")
    callback_url = request.build_absolute_uri(reverse("payments:callback", args=[payment.id]))

    try:
        result = gateway.request_payment(
            amount=payment.amount,
            description=f"قسط دورهٔ {payment.round_number} - وام #{payment.reservation.loan_plan_id}",
            callback_url=callback_url,
            mobile=request.user.phone_number,
        )
    except PaymentError as exc:
        messages.error(request, f"اتصال به درگاه پرداخت ناموفق بود: {exc}")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    payment.gateway = gateway.name
    payment.gateway_authority = result.get("authority", "")
    payment.save(update_fields=["gateway", "gateway_authority"])

    if gateway.name == "manual":
        messages.info(
            request,
            "این وام از حالت واریز دستی استفاده می‌کند. مبلغ قسط را واریز کرده و منتظر تأیید مدیر بمانید.",
        )
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    return redirect(result["redirect_url"])


@login_required
def callback(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.reservation.user_id != request.user.id:
        raise PermissionDenied

    authority = request.GET.get("Authority")
    status = request.GET.get("Status")

    if payment.status == PaymentStatus.PAID:
        messages.info(request, "این قسط قبلاً تأیید شده است.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    if status != "OK":
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=["status"])
        messages.error(request, "پرداخت لغو یا ناموفق بود.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    # Authority باید دقیقاً متعلق به همین قسط باشد. در غیر این صورت، کاربری که
    # چند قسط هم‌مبلغ دارد می‌تواند Authority یک تراکنش را برای قسط دیگری بفرستد.
    if not authority or authority != payment.gateway_authority:
        messages.error(request, "شناسهٔ بازگشتی درگاه با این قسط مطابقت ندارد.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    # گیت‌ویِ تأیید باید همان گیت‌وی‌ای باشد که `pay()` برای همین قسط تنظیم کرده
    # (فیلد `payment.gateway`). در حالت `both` اگر از get_gateway() بدون نام استفاده
    # کنیم، callback همیشه با گیت‌وی دستی تأیید می‌شود و پرداخت‌های زرین‌پال
    # همیشه «ناموفق» ثبت می‌شوند.
    gateway = get_gateway(payment.gateway or None)
    try:
        # مبلغ از رکورد سرور خوانده می‌شود، نه از پارامتر ورودی — تا کاربر نتواند مبلغ را دستکاری کند.
        result = gateway.verify_payment(amount=payment.amount, authority=authority)
    except PaymentError as exc:
        messages.error(request, f"تأیید پرداخت با خطا مواجه شد: {exc}")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    if result["ok"]:
        payment.status = PaymentStatus.PAID
        payment.paid_at = timezone.now()
        payment.gateway_ref = str(result.get("ref_id") or "")
        payment.save(update_fields=["status", "paid_at", "gateway_ref"])
        log_action(
            request.user, "payment_verified",
            {"payment_id": payment.id, "ref_id": result.get("ref_id")},
            request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "پرداخت با موفقیت تأیید شد.")
    else:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=["status"])
        messages.error(request, "تأیید پرداخت ناموفق بود.")

    return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)


@login_required
@require_POST
def submit_manual_receipt(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.reservation.user_id != request.user.id:
        raise PermissionDenied
    if settings.PAYMENT_GATEWAY not in ("manual", "both"):
        raise PermissionDenied
    if payment.status == PaymentStatus.PAID:
        messages.info(request, "این قسط قبلاً تأیید شده است.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    form = ManualReceiptForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "رسید قابل پذیرش نیست. لطفاً اطلاعات و تصویر را بررسی کنید.")
        return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)

    payment.gateway = "manual"
    payment.manual_receipt = form.cleaned_data["receipt"]
    payment.manual_reference = form.cleaned_data["reference"].strip()
    payment.receipt_submitted_at = timezone.now()
    payment.status = PaymentStatus.PENDING
    payment.receipt_rejection_reason = ""
    payment.save(update_fields=["gateway", "manual_receipt", "manual_reference", "receipt_submitted_at", "status", "receipt_rejection_reason"])
    log_action(request.user, "manual_receipt_submitted", {"payment_id": payment.id, "reference": payment.manual_reference}, request.META.get("REMOTE_ADDR"))
    messages.success(request, "رسید ثبت شد و پس از بررسی مدیر، وضعیت قسط به‌روزرسانی می‌شود.")
    return redirect("loans:plan_detail", plan_id=payment.reservation.loan_plan_id)


@staff_member_required
def view_manual_receipt(request, payment_id):
    """رسید یک مدرک مالی است و فقط مدیر صندوق اجازهٔ مشاهدهٔ آن را دارد."""
    payment = get_object_or_404(Payment, pk=payment_id)
    if not payment.manual_receipt:
        raise Http404
    # "image/*" یک MIME wildcard نامعتبر است؛ نوع صحیح را از پسوند فایل بگیریم
    # (تصاویر رسید فقط jpg/jpeg/png/webp مجازند).
    content_type = mimetypes.guess_type(payment.manual_receipt.name)[0] or "application/octet-stream"
    return FileResponse(payment.manual_receipt.open("rb"), content_type=content_type)
