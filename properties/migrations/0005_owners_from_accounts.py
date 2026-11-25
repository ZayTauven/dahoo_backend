from django.db import migrations


def owners_from_accounts(apps, schema_editor):
    """Chaque bailleur rattaché comme simple compte reçoit une fiche dans l'agence du bien."""
    Property = apps.get_model("properties", "Property")
    Owner = apps.get_model("owners", "Owner")
    for item in Property.objects.filter(owner__isnull=False).select_related("owner"):
        user = item.owner
        owner, _ = Owner.objects.get_or_create(
            organization_id=item.organization_id,
            user=user,
            defaults={"first_name": user.first_name, "last_name": user.last_name, "email": user.email or ""},
        )
        item.owner_profile = owner
        item.save(update_fields=["owner_profile"])


class Migration(migrations.Migration):

    dependencies = [("properties", "0004_property_owner_profile")]

    operations = [migrations.RunPython(owners_from_accounts, migrations.RunPython.noop)]
