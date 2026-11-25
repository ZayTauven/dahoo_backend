from django.apps import AppConfig


class MailingConfig(AppConfig):
    name = "mailing"
    verbose_name = "E-mails"

    def ready(self):
        from mailing import signals  # noqa: F401
