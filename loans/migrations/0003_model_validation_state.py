from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loans", "0002_financial_integrity_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="loanplan",
            name="capacity",
            field=models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="ظرفیت (حداکثر تعداد عضو)"),
        ),
        migrations.AlterField(
            model_name="loanplan",
            name="duration_months",
            field=models.PositiveIntegerField(help_text="هم تعداد اقساط و هم تعداد قرعه‌کشی‌های این طرح.", validators=[MinValueValidator(1)], verbose_name="تعداد دوره / ماه"),
        ),
        migrations.AlterField(
            model_name="loanplan",
            name="monthly_payment",
            field=models.DecimalField(decimal_places=0, max_digits=14, validators=[MinValueValidator(1)], verbose_name="قسط ماهانه هر عضو (تومان)"),
        ),
        migrations.AlterField(
            model_name="loanplan",
            name="service_fee",
            field=models.DecimalField(decimal_places=0, default=0, help_text="هزینهٔ اداره صندوق، نه سود/بهره — این صندوق قرض‌الحسنه (بدون سود) است.", max_digits=14, validators=[MinValueValidator(0)], verbose_name="هزینهٔ خدمات صندوق (تومان)"),
        ),
        migrations.AlterField(
            model_name="loanplan",
            name="total_amount",
            field=models.DecimalField(decimal_places=0, max_digits=14, validators=[MinValueValidator(1)], verbose_name="مبلغ کل وام (تومان)"),
        ),
        migrations.AlterField(
            model_name="lotterydraw",
            name="round_number",
            field=models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="شمارهٔ دوره"),
        ),
    ]
