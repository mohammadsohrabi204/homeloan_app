from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("loans", "0006_payment_destination")]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160, verbose_name="عنوان")),
                ("message", models.TextField(verbose_name="پیام")),
                ("is_read", models.BooleanField(default=False, verbose_name="خوانده شده")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="loans.payment")),
                ("lottery_draw", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="loans.lotterydraw")),
                ("kind", models.CharField(default="general", max_length=40)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "اعلان", "verbose_name_plural": "اعلان‌ها"},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(fields=["user", "payment", "kind"], name="uq_user_payment_notification_kind"),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(fields=["user", "lottery_draw", "kind"], name="uq_user_draw_notification_kind"),
        ),
    ]
