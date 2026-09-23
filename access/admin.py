from django.contrib import admin

from .models import Capability, Role, RoleCapability


class RoleCapabilityInline(admin.TabularInline):
    model = RoleCapability
    extra = 1
    autocomplete_fields = ("capability",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'label')
    search_fields = ('code', 'label')
    ordering = ('code',)
    inlines = [RoleCapabilityInline]


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')
    ordering = ('code',)
