from django.contrib import admin

from .models import Expense, Owner, OwnerPayout


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "organization", "user", "created_at")
    list_filter = ("organization",)
    search_fields = ("first_name", "last_name", "user__phone")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("label", "organization", "property", "category", "amount", "spent_on")
    list_filter = ("organization", "category")


@admin.register(OwnerPayout)
class OwnerPayoutAdmin(admin.ModelAdmin):
    list_display = ("owner", "organization", "amount", "paid_on", "channel", "cancelled_at")
    list_filter = ("organization", "channel")
