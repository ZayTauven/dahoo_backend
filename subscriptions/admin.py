from django.contrib import admin

from .models import BillingSettings, PlanRequest, Subscription, SubscriptionPayment, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'audience', 'billing_type', 'price', 'commission_rate', 'active', 'limits_trial')
    list_filter = ('billing_type', 'audience', 'active')
    search_fields = ('name',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'plan', 'price', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'plan', 'start_date')
    search_fields = ('organization__name', 'plan__name')
    ordering = ('-start_date',)
    readonly_fields = ('created_at',)


# Un règlement s'enregistre et s'annule dans l'espace plateforme (il déplace l'échéance) : lecture seule ici.
@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscription', 'amount', 'period_start', 'period_end', 'paid_on', 'cancelled_at')
    search_fields = ('subscription__organization__name', 'reference')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([PlanRequest, BillingSettings])
