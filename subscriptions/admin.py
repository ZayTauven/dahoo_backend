from django.contrib import admin
from .models import SubscriptionPlan, Subscription, SubscriptionPayment


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'billing_type', 'price', 'commission_rate', 'active')
    list_filter = ('billing_type', 'active')
    search_fields = ('name',)
    list_editable = ('active',)
    fieldsets = (
        ('Informations', {'fields': ('name', 'billing_type', 'active')}),
        ('Tarification', {'fields': ('price', 'commission_rate')}),
        ('Limites', {'fields': ('max_properties', 'max_units', 'max_users')}),
    )


class SubscriptionPaymentInline(admin.TabularInline):
    model = SubscriptionPayment
    extra = 0
    fields = ('payment',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'plan', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'plan', 'start_date')
    search_fields = ('owner__phone', 'plan__name')
    ordering = ('-start_date',)
    readonly_fields = ('created_at',)
    inlines = [SubscriptionPaymentInline]
    fieldsets = (
        ('Propriétaire', {'fields': ('owner',)}),
        ('Plan', {'fields': ('plan', 'status')}),
        ('Dates', {'fields': ('start_date', 'end_date', 'created_at')}),
    )


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'payment')
    search_fields = ('subscription__id', 'payment__id')
