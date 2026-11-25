from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    """
    Fichiers qui ne doivent jamais être servis par le serveur web (intérieur des logements). Ils se lisent
    uniquement par un lien signé, voir inspections.photos.
    """

    def __init__(self):
        super().__init__()

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    def url(self, name):
        raise ValueError("Ce fichier n'a pas d'adresse publique.")
