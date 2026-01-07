from django.contrib import admin
from .models import MaintenanceCategory, MaintenanceTicket, MaintenanceAssignment, MaintenanceLog


@admin.register(MaintenanceCategory)
class MaintenanceCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'label')
    search_fields = ('code', 'label')
    ordering = ('code',)


class MaintenanceAssignmentInline(admin.TabularInline):
    model = MaintenanceAssignment
    extra = 1
    fields = ('assigned_to', 'assigned_by', 'assigned_at')
    readonly_fields = ('assigned_at',)


class MaintenanceLogInline(admin.TabularInline):
    model = MaintenanceLog
    extra = 0
    fields = ('user', 'message', 'created_at')
    readonly_fields = ('user', 'message', 'created_at')


@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'unit', 'category', 'priority', 'status', 'reported_by', 'created_at')
    list_filter = ('status', 'priority', 'category', 'created_at')
    search_fields = ('unit__reference', 'category__label', 'reported_by__phone')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MaintenanceAssignmentInline, MaintenanceLogInline]
    fieldsets = (
        ('Ticket', {'fields': ('unit', 'category', 'reported_by')}),
        ('Description', {'fields': ('description',)}),
        ('Statut', {'fields': ('priority', 'status')}),
        ('Dates', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(MaintenanceAssignment)
class MaintenanceAssignmentAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'assigned_to', 'assigned_by', 'assigned_at')
    list_filter = ('assigned_at',)
    search_fields = ('ticket__id', 'assigned_to__phone', 'assigned_by__phone')
    readonly_fields = ('assigned_at',)


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('ticket__id', 'user__phone', 'message')
    readonly_fields = ('created_at',)
