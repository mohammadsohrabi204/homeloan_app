from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loans", "0004_payment_manual_receipt"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="receipt_rejection_reason",
            field=models.CharField(blank=True, max_length=250, verbose_name="علت رد رسید"),
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(choices=[("pending", "در انتظار پرداخت"), ("paid", "پرداخت‌شده"), ("receipt_rejected", "رسید رد شده"), ("failed", "ناموفق")], default="pending", max_length=20),
        ),
    ]
