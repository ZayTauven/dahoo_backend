from django.contrib import admin

from .models import EmailOptOut, OutgoingEmail


@admin.register(OutgoingEmail)
class OutgoingEmailAdmin(admin.ModelAdmin):
    list_display = ("template", "to", "organization", "status", "attempts", "created_at", "sent_at")
    list_filter = ("status", "template")
    search_fields = ("to",)
    readonly_fields = [field.name for field in OutgoingEmail._meta.fields]


@admin.register(EmailOptOut)
class EmailOptOutAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "created_at")
    search_fields = ("email",)
