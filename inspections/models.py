import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from inspections.storage import PrivateStorage

User = settings.AUTH_USER_MODEL


# État des lieux d'un bail : un à l'entrée, un à la sortie. Validé, il ne se modifie plus.
class Inspection(models.Model):
    KINDS = [
        ("ENTRY", "Entrée"),
        ("EXIT", "Sortie"),
    ]
    STATUS = [
        ("DRAFT", "En cours"),
        ("SIGNED", "Validé"),
    ]

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="inspections")
    lease = models.ForeignKey("leases.LeaseContract", on_delete=models.CASCADE, related_name="inspections")
    kind = models.CharField(max_length=10, choices=KINDS)
    status = models.CharField(max_length=10, choices=STATUS, default="DRAFT")
    done_on = models.DateField(default=timezone.localdate)

    electricity_reading = models.CharField(max_length=30, blank=True)
    water_reading = models.CharField(max_length=30, blank=True)
    keys_count = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)

    # Renseignés à la validation.
    tenant_signer = models.CharField("présent pour le locataire", max_length=150, blank=True)
    tenant_remarks = models.TextField("réserves du locataire", blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "id"]
        constraints = [
            models.UniqueConstraint(fields=["lease", "kind"], name="one_inspection_per_lease_and_kind"),
        ]

    def __str__(self):
        return f"État des lieux {self.get_kind_display().lower()} · bail {self.lease_id}"

    @property
    def number(self):
        return f"E{self.done_on:%Y%m}-{self.pk}"


class InspectionItem(models.Model):
    CONDITIONS = [
        ("NEW", "Neuf"),
        ("GOOD", "Bon"),
        ("WORN", "Usé"),
        ("DAMAGED", "Dégradé"),
        ("MISSING", "Manquant"),
    ]
    # Ce qui se reproche au locataire ; l'usure normale reste au bailleur.
    FAULTS = ("DAMAGED", "MISSING")

    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="items")
    room = models.CharField(max_length=60)
    label = models.CharField(max_length=80)
    # Vide : pas encore regardé.
    condition = models.CharField(max_length=10, choices=CONDITIONS, blank=True)
    note = models.CharField(max_length=300, blank=True)
    position = models.PositiveIntegerField(default=0)
    # À la sortie : le même élément à l'entrée, pour comparer.
    reference = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["position", "id"]


def photo_name(instance, filename):
    return f"inspections/{instance.inspection.organization_id}/{instance.inspection_id}/{uuid.uuid4().hex}.jpg"


class InspectionPhoto(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="photos")
    item = models.ForeignKey(InspectionItem, on_delete=models.CASCADE, null=True, blank=True, related_name="photos")
    image = models.ImageField(upload_to=photo_name, storage=PrivateStorage())
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


@receiver(post_delete, sender=InspectionPhoto)
def delete_photo_file(sender, instance, **kwargs):
    if instance.image:
        storage, name = instance.image.storage, instance.image.name
        transaction.on_commit(lambda: storage.delete(name))
