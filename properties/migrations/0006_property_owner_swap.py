from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("properties", "0005_owners_from_accounts")]

    operations = [
        migrations.RemoveField(model_name="property", name="owner"),
        migrations.RenameField(model_name="property", old_name="owner_profile", new_name="owner"),
    ]
