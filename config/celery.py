import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("homeloan")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "payment-notifications-every-hour": {
        "task": "loans.tasks.create_payment_notifications",
        "schedule": 3600.0,
    },
}
