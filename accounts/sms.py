"""ارسال پیامک؛ در توسعه کد در لاگ ثبت می‌شود، در تولید باید سرویس پیامکی پیکربندی شود."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_phone_otp(phone_number, code):
    text = f"کد تأیید صندوق وام خانگی: {code}. این کد تا {settings.PHONE_OTP_TTL_MINUTES} دقیقه معتبر است."
    if settings.DEBUG and settings.SMS_BACKEND == "console":
        logger.info("PHONE OTP for %s: %s", phone_number, code)
        return True
    if settings.SMS_BACKEND != "kavenegar" or not settings.KAVENEGAR_API_KEY or not settings.KAVENEGAR_SENDER:
        return False
    try:
        response = requests.get(
            f"https://api.kavenegar.com/v1/{settings.KAVENEGAR_API_KEY}/sms/send.json",
            params={"receptor": phone_number, "sender": settings.KAVENEGAR_SENDER, "message": text}, timeout=15,
        )
        response.raise_for_status()
        return response.json().get("return", {}).get("status") == 200
    except requests.RequestException:
        logger.exception("SMS delivery failed")
        return False
