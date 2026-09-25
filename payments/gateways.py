"""
لایهٔ انتزاعی درگاه پرداخت. هدف این است که تعویض یا افزودن یک درگاه دیگر
(آی‌دی‌پی، نکست‌پی، پی.آی‌آر، Stripe و ...) فقط به یک کلاس جدید نیاز داشته باشد،
بدون تغییر در views یا مدل‌ها.

نکتهٔ امنیتی مهم: مبلغِ verify_payment همیشه باید از رکورد سرور (Payment.amount در
دیتابیس خودمان) خوانده شود، هرگز از پارامتری که کاربر/مرورگر می‌فرستد — در غیر این
صورت کاربر می‌تواند مبلغ را دستکاری کند.
"""
import hashlib

import requests
from django.conf import settings


class PaymentError(Exception):
    pass


class BasePaymentGateway:
    name = "base"

    def request_payment(self, amount, description, callback_url, mobile=None):
        raise NotImplementedError

    def verify_payment(self, amount, authority=None, **kwargs):
        raise NotImplementedError


class ManualGateway(BasePaymentGateway):
    """
    گزینهٔ پیش‌فرض/توسعه: هیچ اتصال اینترنتی واقعی برقرار نمی‌کند.
    مناسب برای مدل «واریز کارت‌به‌کارت + تأیید دستی توسط مدیر در پنل ادمین»
    که در بسیاری از صندوق‌های قرض‌الحسنهٔ کوچک رایج است، و برای تست محلی بدون
    نیاز به merchant_id واقعی.
    """

    name = "manual"

    def request_payment(self, amount, description, callback_url, mobile=None):
        fake_authority = hashlib.sha1(f"{amount}-{description}".encode("utf-8")).hexdigest()[:20]
        return {
            "redirect_url": f"{callback_url}?Authority={fake_authority}&Status=OK",
            "authority": fake_authority,
        }

    def verify_payment(self, amount, authority=None, **kwargs):
        # در حالت دستی، تأیید نهایی همیشه بر عهدهٔ مدیر (اکشن «تأیید دستی پرداخت» در پنل) است.
        return {"ok": False, "ref_id": None, "raw": {"note": "manual confirmation required"}}


class ZarinPalGateway(BasePaymentGateway):
    """
    پیاده‌سازی بر اساس REST API نسخهٔ v4 زرین‌پال (payment.zarinpal.com/pg/v4/...).
    مهم: پیش از استفادهٔ واقعی، حتماً با مستندات فعلی zarinpal.com/docs و merchant_id
    آزمایشی خودتان در sandbox تست کنید — APIهای درگاه‌های پرداخت گاهی تغییر می‌کنند.
    """

    name = "zarinpal"

    REQUEST_URL = "https://payment.zarinpal.com/pg/v4/payment/request.json"
    VERIFY_URL = "https://payment.zarinpal.com/pg/v4/payment/verify.json"
    STARTPAY_URL = "https://payment.zarinpal.com/pg/StartPay/{authority}"

    SANDBOX_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    SANDBOX_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
    SANDBOX_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

    def __init__(self, merchant_id, sandbox=True):
        if not merchant_id:
            raise PaymentError("ZARINPAL_MERCHANT_ID تنظیم نشده است.")
        self.merchant_id = merchant_id
        self.sandbox = sandbox

    def request_payment(self, amount, description, callback_url, mobile=None):
        url = self.SANDBOX_REQUEST_URL if self.sandbox else self.REQUEST_URL
        payload = {
            "merchant_id": self.merchant_id,
            "amount": int(amount),
            "currency": "IRT",  # مبلغ‌های ما در برنامه به تومان هستن، نه ریال
            "description": description,
            "callback_url": callback_url,
        }   
        if mobile:
            payload["metadata"] = {"mobile": mobile}

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as exc:
            raise PaymentError(f"ارتباط با درگاه پرداخت برقرار نشد: {exc}") from exc

        data = body.get("data") or {}
        if data.get("code") != 100:
            raise PaymentError(f"خطا در درخواست پرداخت: {body.get('errors') or data}")

        authority = data["authority"]
        start_url = (self.SANDBOX_STARTPAY_URL if self.sandbox else self.STARTPAY_URL).format(authority=authority)
        return {"redirect_url": start_url, "authority": authority}

    def verify_payment(self, amount, authority=None, **kwargs):
        url = self.SANDBOX_VERIFY_URL if self.sandbox else self.VERIFY_URL
        payload = {"merchant_id": self.merchant_id, "amount": int(amount), "currency": "IRT", "authority": authority}

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as exc:
            raise PaymentError(f"ارتباط با درگاه پرداخت برقرار نشد: {exc}") from exc

        data = body.get("data") or {}
        if data.get("code") in (100, 101):  # 101 یعنی قبلاً هم تأیید شده بود
            return {"ok": True, "ref_id": data.get("ref_id"), "raw": body}
        return {"ok": False, "ref_id": None, "raw": body}


def get_gateway(name=None):
    name = name or getattr(settings, "PAYMENT_GATEWAY", "manual")
    if name == "zarinpal":
        return ZarinPalGateway(
            merchant_id=settings.ZARINPAL_MERCHANT_ID, sandbox=settings.ZARINPAL_SANDBOX
        )
    return ManualGateway()
