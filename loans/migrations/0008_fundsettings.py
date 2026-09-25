from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("loans", "0007_notification"),
    ]

    operations = [
        migrations.CreateModel(
            name="FundSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fund_name", models.CharField(default="صندوق وام خانگی", max_length=150, verbose_name="نام صندوق")),
                ("support_phone", models.CharField(blank=True, max_length=20, verbose_name="شماره پشتیبانی")),
                ("support_text", models.CharField(blank=True, max_length=300, verbose_name="متن پشتیبانی")),
                ("payment_instructions", models.TextField(blank=True, help_text="متنی که به کاربران برای پرداخت اقساط نمایش داده می‌شود.", verbose_name="راهنمای پرداخت")),
                ("terms_text", models.TextField(blank=True, help_text="قوانین عمومی عضویت و پرداخت صندوق.", verbose_name="قوانین و شرایط")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")),
            ],
            options={
                "verbose_name": "تنظیمات صندوق",
                "verbose_name_plural": "تنظیمات صندوق",
            },
        ),
    ]
