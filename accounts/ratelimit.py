"""
یک محدودکنندهٔ نرخ درخواست ساده و شفاف، بر پایهٔ فریم‌ورک cache خود جنگو.
هدف: کاهش امکان حملهٔ Brute-force روی فرم ورود/ثبت‌نام.

توجه: بک‌اند پیش‌فرض cache در settings.py حافظه‌محلی (LocMemCache) است که برای
یک پردازش/سرور واحد کافی است. اگر برنامه را با چند worker/سرور اجرا می‌کنید،
یک بک‌اند مشترک مثل Redis برای CACHES تنظیم کنید تا شمارش بین پردازش‌ها یکسان بماند.
"""

from django.core.cache import cache


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """
    اگر تعداد تلاش‌های مربوط به `key` در بازهٔ `window_seconds` ثانیهٔ اخیر
    از `limit` بیشتر شده باشد True برمی‌گرداند (یعنی درخواست باید مسدود شود).
    """
    cache_key = f"ratelimit:{key}"
    current = cache.get(cache_key)

    if current is None:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False

    if current >= limit:
        return True

    try:
        cache.incr(cache_key)
    except ValueError:
        # کلید بین get و incr منقضی شده — دوباره از صفر شروع می‌کنیم
        cache.set(cache_key, 1, timeout=window_seconds)

    return False
