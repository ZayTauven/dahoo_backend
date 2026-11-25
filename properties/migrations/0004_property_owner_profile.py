import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("owners", "0001_initial"),
        ("properties", "0003_property_location_unit_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="owner_profile",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="properties", to="owners.owner",
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="commission_rate",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
    ]
