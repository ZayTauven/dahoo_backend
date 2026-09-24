from django.db import models


# Rôles communs à toutes les organisations, gérés par l'admin Dahoo (admin Django).
# Les rôles système (ORG_ADMIN, MANAGER...) sont réalignés sur access/catalog.py à chaque migrate :
# pour un besoin spécifique, créer un nouveau rôle plutôt que modifier un rôle système.
class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    capabilities = models.ManyToManyField("Capability", through="RoleCapability", related_name="roles")

    def __str__(self):
        return self.code


class Capability(models.Model):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code


class RoleCapability(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    capability = models.ForeignKey(Capability, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("role", "capability")
