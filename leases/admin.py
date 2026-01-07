from django.contrib import admin
from .models import LeaseContract, SaleContract


@admin.register(LeaseContract)
class LeaseContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'unit', 'tenant', 'owner', 'start_date', 'end_date', 'rent_amount', 'status')
    list_filter = ('status', 'payment_frequency', 'start_date')
    search_fields = ('unit__reference', 'tenant__phone', 'owner__phone')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Unité & Parties', {'fields': ('unit', 'owner', 'tenant')}),
        ('Dates', {'fields': ('start_date', 'end_date', 'signed_at', 'created_at')}),
        ('Montants', {'fields': ('rent_amount', 'charges_amount', 'deposit_amount')}),
        ('Paiement', {'fields': ('payment_frequency',)}),
        ('Statut', {'fields': ('status',)}),
    )


@admin.register(SaleContract)
class SaleContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'unit', 'buyer', 'owner', 'sale_price', 'agreed_date', 'status')
    list_filter = ('status', 'agreed_date')
    search_fields = ('unit__reference', 'buyer__phone', 'owner__phone')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Unité & Parties', {'fields': ('unit', 'owner', 'buyer')}),
        ('Prix & Commission', {'fields': ('sale_price', 'commission_amount')}),
        ('Dates', {'fields': ('agreed_date', 'transfer_date', 'signed_at', 'created_at')}),
        ('Statut', {'fields': ('status',)}),
    )
