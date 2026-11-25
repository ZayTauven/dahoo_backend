from django.contrib import admin

from .models import Inspection


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("id", "lease", "kind", "status", "done_on", "organization")
    list_filter = ("kind", "status")
