from django.contrib import admin

from .models import DemoRequest


@admin.register(DemoRequest)
class DemoRequestAdmin(admin.ModelAdmin):
    list_display = ("agency_name", "contact_name", "phone", "city", "units_range", "handled", "created_at")
    list_filter = ("handled", "units_range", "city")
    search_fields = ("agency_name", "contact_name", "phone", "email")
    list_editable = ("handled",)
    ordering = ("-created_at",)
