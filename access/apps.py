from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_capabilities(sender, **kwargs):
    from access.services import sync_capabilities

    sync_capabilities()


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "access"

    def ready(self):
        post_migrate.connect(_sync_capabilities, sender=self, dispatch_uid="access.sync_capabilities")
