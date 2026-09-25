from datetime import date, datetime

from django.utils import timezone

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def gregorian_to_jalali(year, month, day):
    """تبدیل تاریخ میلادی به جلالی، بدون وابستگی به کتابخانهٔ بیرونی."""
    month_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    adjusted_year = year + 1 if month > 2 else year
    days = 355666 + (365 * year) + ((adjusted_year + 3) // 4) - ((adjusted_year + 99) // 100) + ((adjusted_year + 399) // 400) + day + month_days[month - 1]
    jalali_year = -1595 + (33 * (days // 12053))
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    jalali_month = 1 + (days // 31) if days < 186 else 7 + ((days - 186) // 30)
    jalali_day = 1 + (days % 31) if days < 186 else 1 + ((days - 186) % 30)
    return jalali_year, jalali_month, jalali_day


def format_jalali(value):
    if not isinstance(value, (date, datetime)):
        return "—"
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    year, month, day = gregorian_to_jalali(value.year, value.month, value.day)
    result = f"{year:04d}/{month:02d}/{day:02d}"
    if isinstance(value, datetime):
        result += f" {value:%H:%M}"
    return result.translate(PERSIAN_DIGITS)
