import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("loans", "0005_payment_receipt_rejection")]

    operations = [
        migrations.CreateModel(
            name="PaymentDestination",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100, verbose_name="عنوان حساب")),
                ("account_holder", models.CharField(max_length=120, verbose_name="نام صاحب حساب")),
                ("card_number", models.CharField(blank=True, max_length=16, verbose_name="شماره کارت")),
                ("iban", models.CharField(blank=True, max_length=26, verbose_name="شماره شبا")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
            ],
            options={"verbose_name": "حساب دریافت اقساط", "verbose_name_plural": "حساب‌های دریافت اقساط"},
        ),
        migrations.AddField(
            model_name="loanplan",
            name="payment_destination",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="loan_plans", to="loans.paymentdestination", verbose_name="حساب دریافت اقساط"),
        ),
    ]
