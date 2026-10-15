from django import template

from loans.jalali import amount_in_words, format_jalali

register = template.Library()


@register.filter
def amount_words(value):
    return amount_in_words(value)


@register.filter
def jalali(value):
    return format_jalali(value)


@register.simple_tag
def current_jalali_year():
    from django.utils import timezone
    return format_jalali(timezone.localdate()).split("/")[0]
