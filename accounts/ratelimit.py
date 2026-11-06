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
    # add() establishes the window once, while incr() is atomic on Redis and
    # Django's local-memory backend. This avoids lost increments under load.
    cache.add(cache_key, 0, timeout=window_seconds)
    try:
        current = cache.incr(cache_key)
    except ValueError:
        # Key expired between add and incr; start a fresh window.
        cache.add(cache_key, 0, timeout=window_seconds)
        current = cache.incr(cache_key)
    return current > limit
