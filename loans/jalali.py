from datetime import date, datetime
from django.utils import timezone

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def gregorian_to_jalali(year, month, day):
    gy, gm, gd = year, month, day
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0):
        g_days_in_month[1] = 29

    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1

    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    g_day_no += gd2

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + (j_day_no - 186) % 30
    return jy, jm, jd


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


_PERSIAN_ONES = ("صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده")
_PERSIAN_TENS = ("", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود")
_PERSIAN_HUNDREDS = ("", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد")
_PERSIAN_SCALES = ("", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون")


def _under_thousand_words(number):
    parts = []
    hundreds, rest = divmod(number, 100)
    if hundreds:
        parts.append(_PERSIAN_HUNDREDS[hundreds])
    if rest:
        if rest < 20:
            parts.append(_PERSIAN_ONES[rest])
        else:
            tens, ones = divmod(rest, 10)
            parts.append(_PERSIAN_TENS[tens])
            if ones:
                parts.append(_PERSIAN_ONES[ones])
    return " و ".join(parts)


def amount_in_words(value):
    """تبدیل مبلغ صحیح به حروف فارسی."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number == 0:
        return "صفر تومان"
    if number < 0:
        return "منفی " + amount_in_words(-number)

    parts = []
    scale = 0
    while number:
        group = number % 1000
        if group:
            text = _under_thousand_words(group)
            if scale:
                text += " " + _PERSIAN_SCALES[scale]
            parts.append(text)
        number //= 1000
        scale += 1
    return " و ".join(reversed(parts)) + " تومان"


def jalali_to_gregorian(jyear, jmonth, jday):
    jyear = int(jyear); jmonth = int(jmonth); jday = int(jday)
    jy = jyear - 979
    days = 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4)
    if jmonth <= 6:
        days += (jmonth - 1) * 31
    else:
        days += (jmonth - 7) * 30 + 186
    days += jday - 1
    gday = days + 79
    gy = 1600 + 400 * (gday // 146097)
    gday %= 146097
    leap = True
    if gday >= 36525:
        gday -= 1
        gy += 100 * (gday // 36524)
        gday %= 36524
        if gday < 365:
            leap = False
        else:
            gday += 1
    gy += 4 * (gday // 1461)
    gday %= 1461
    if gday >= 366:
        leap = False
        gday -= 1
        gy += gday // 365
        gday %= 365
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gday >= month_days[gm - 1]:
        gday -= month_days[gm - 1]
        gm += 1
    return gy, gm, gday + 1
