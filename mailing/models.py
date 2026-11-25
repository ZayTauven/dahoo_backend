from django.db import models


# File d'envoi. Un e-mail est d'abord enregistré, puis envoyé : un serveur SMTP en panne ne perd rien et
# ne fait jamais échouer l'action qui l'a déclenché.
class OutgoingEmail(models.Model):
    STATUS = [
        ("PENDING", "À envoyer"),
        ("SENT", "Envoyé"),
        ("FAILED", "Échec"),
        ("SKIPPED", "Non envoyé"),
    ]

    # Vide pour les messages du compte (mot de passe, bienvenue) et de l'équipe Dahoo.
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, null=True, blank=True, related_name="outgoing_emails"
    )
    to = models.EmailField()
    # Gabarit et variables (texte seulement) : le message est fabriqué à l'envoi.
    template = models.CharField(max_length=50)
    context = models.JSONField(default=dict)

    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    # Un rappel ne part qu'une fois : même clé, même message.
    dedupe_key = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["dedupe_key"], condition=~models.Q(dedupe_key=""), name="outgoing_email_unique_dedupe"),
        ]

    def __str__(self):
        return f"{self.template} → {self.to}"


# Une personne qui ne veut plus recevoir les rappels d'une agence (lien au bas de chaque message).
class EmailOptOut(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="email_opt_outs")
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "email"], name="unique_email_opt_out")]
