from django.db import migrations


def freeze_prices(apps, schema_editor):
    """Les abonnements existants gardent le prix actuel de leur offre."""
    for subscription in apps.get_model("subscriptions", "Subscription").objects.filter(price__isnull=True).select_related("plan"):
        subscription.price = subscription.plan.price
        subscription.save(update_fields=["price"])


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0004_billing")]

    operations = [migrations.RunPython(freeze_prices, migrations.RunPython.noop)]
