from django.db import migrations


def refuse_if_used(apps, schema_editor):
    """L'ancien lien vers le paiement d'un locataire n'a jamais servi ; on ne détruit rien s'il contient des lignes."""
    if apps.get_model("subscriptions", "SubscriptionPayment").objects.exists():
        raise RuntimeError("subscriptions_subscriptionpayment contient des lignes : les reprendre avant cette migration.")


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0002_remove_subscription_owner_subscription_organization")]

    operations = [
        migrations.RunPython(refuse_if_used, migrations.RunPython.noop),
        migrations.DeleteModel("SubscriptionPayment"),
    ]
