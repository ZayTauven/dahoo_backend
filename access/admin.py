from django.contrib import admin
from .models import Role, Capability, RoleCapability, UserRole, UserCapability


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'label')
    search_fields = ('code', 'label')
    ordering = ('code',)


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')
    ordering = ('code',)


@admin.register(RoleCapability)
class RoleCapabilityAdmin(admin.ModelAdmin):
    list_display = ('role', 'capability')
    list_filter = ('role',)
    search_fields = ('role__code', 'capability__code')


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'active')
    list_filter = ('active', 'role')
    search_fields = ('user__phone', 'role__code')
    list_editable = ('active',)


@admin.register(UserCapability)
class UserCapabilityAdmin(admin.ModelAdmin):
    list_display = ('user', 'capability', 'context_type', 'context_id')
    list_filter = ('context_type',)
    search_fields = ('user__phone', 'capability__code')
