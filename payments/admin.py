from django.contrib import admin
from .models import PaymentMethod, PaymentSchedule, Payment, PaymentAllocation


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('code', 'label')
    search_fields = ('code', 'label')
    ordering = ('code',)


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'schedule_type', 'due_date', 'amount_due', 'is_paid')
    list_filter = ('schedule_type', 'is_paid', 'due_date')
    search_fields = ('lease_contract__id', 'sale_contract__id')
    ordering = ('due_date',)
    list_editable = ('is_paid',)
    readonly_fields = ('created_at',)


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 1
    fields = ('schedule', 'allocated_amount')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'payer', 'amount_paid', 'payment_method', 'payment_date')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('payer__phone', 'reference')
    ordering = ('-payment_date',)
    inlines = [PaymentAllocationInline]
    readonly_fields = ('created_at', 'payment_date')


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ('payment', 'schedule', 'allocated_amount')
    list_filter = ('schedule__schedule_type',)
    search_fields = ('payment__id', 'schedule__id')
    readonly_fields = ('created_at',)
