import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loans", "0003_model_validation_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="manual_receipt",
            field=models.ImageField(blank=True, upload_to="payment_receipts/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])], verbose_name="تصویر رسید کارت‌به‌کارت"),
        ),
        migrations.AddField(
            model_name="payment",
            name="manual_reference",
            field=models.CharField(blank=True, max_length=80, verbose_name="شمارهٔ پیگیری واریز"),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt_submitted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="زمان ارسال رسید"),
        ),
    ]
