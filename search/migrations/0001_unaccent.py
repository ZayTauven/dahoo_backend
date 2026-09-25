from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Recherche insensible aux accents (« aissatou » trouve Aïssatou) : extension PostgreSQL unaccent."""

    dependencies = []

    operations = [UnaccentExtension()]
