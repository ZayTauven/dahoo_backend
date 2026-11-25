from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True, null=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    # Seule une adresse confirmée reçoit les données de l'agence et les liens de mot de passe.
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # Préférences : point du jour, alertes immédiates (pannes prioritaires ou confiées).
    email_digest = models.BooleanField(default=True)
    email_alerts = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.first_name} - {self.phone}"

    
