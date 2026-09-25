from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(model_name="user", name="card_number", field=models.CharField(blank=True, max_length=16, verbose_name="شماره کارت برای دریافت وام")),
        migrations.AddField(model_name="user", name="iban", field=models.CharField(blank=True, max_length=26, verbose_name="شماره شبای برای دریافت وام")),
        migrations.AddField(model_name="user", name="phone_verified", field=models.BooleanField(default=False, verbose_name="شماره موبایل تأیید شده")),
        migrations.AddField(model_name="user", name="phone_otp_hash", field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name="user", name="phone_otp_expires_at", field=models.DateTimeField(blank=True, null=True)),
    ]
