from django.contrib import admin

from .models import DepositSettlement


# Un décompte s'enregistre et s'annule dans l'espace agence : lecture seule ici.
@admin.register(DepositSettlement)
class DepositSettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "lease", "held_amount", "refund_amount", "settled_on", "cancelled_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
