from django.db import migrations

from users.phone import normalize_phone


def normalize_existing_phones(apps, schema_editor):
    """
    Met les numéros existants au format unique (+221…) utilisé à la connexion.
    Un numéro qui entrerait en conflit avec un compte existant n'est pas modifié (à fusionner à la main).
    """
    User = apps.get_model("users", "User")
    taken = set(User.objects.values_list("phone", flat=True))
    for user in User.objects.all():
        phone = normalize_phone(user.phone)
        if phone == user.phone:
            continue
        if phone in taken:
            print(f"\n  Numéro {user.phone} (compte {user.pk}) non normalisé : {phone} existe déjà.")
            continue
        taken.discard(user.phone)
        taken.add(phone)
        user.phone = phone
        user.save(update_fields=["phone"])


class Migration(migrations.Migration):
    dependencies = [("users", "0003_delete_capability")]

    operations = [migrations.RunPython(normalize_existing_phones, migrations.RunPython.noop)]
