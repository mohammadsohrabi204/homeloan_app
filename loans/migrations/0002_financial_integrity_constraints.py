from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loans", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="loanplan",
            constraint=models.CheckConstraint(condition=models.Q(("total_amount__gt", 0)), name="loan_total_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="loanplan",
            constraint=models.CheckConstraint(condition=models.Q(("monthly_payment__gt", 0)), name="loan_monthly_payment_positive"),
        ),
        migrations.AddConstraint(
            model_name="loanplan",
            constraint=models.CheckConstraint(condition=models.Q(("service_fee__gte", 0)), name="loan_service_fee_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="loanplan",
            constraint=models.CheckConstraint(condition=models.Q(("duration_months__gt", 0)), name="loan_duration_positive"),
        ),
        migrations.AddConstraint(
            model_name="loanplan",
            constraint=models.CheckConstraint(condition=models.Q(("capacity__gt", 0)), name="loan_capacity_positive"),
        ),
        migrations.AddConstraint(
            model_name="lotterydraw",
            constraint=models.CheckConstraint(condition=models.Q(("round_number__gt", 0)), name="lottery_round_positive"),
        ),
    ]
