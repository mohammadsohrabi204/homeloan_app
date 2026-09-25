from celery import shared_task

from .services import notify_upcoming_and_overdue_payments


@shared_task
def create_payment_notifications():
    return notify_upcoming_and_overdue_payments()
