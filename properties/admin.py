from django.contrib import admin
from .models import Property, Building, Unit


class BuildingInline(admin.TabularInline):
    model = Building
    extra = 1
    fields = ('name',)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'city', 'created_at')
    list_filter = ('city', 'created_at')
    search_fields = ('name', 'address', 'city', 'owner__phone')
    ordering = ('-created_at',)
    inlines = [BuildingInline]


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 1
    fields = ('reference', 'unit_type', 'surface', 'status')


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'property', 'unit_count')
    list_filter = ('property__name',)
    search_fields = ('name', 'property__name')
    inlines = [UnitInline]
    
    def unit_count(self, obj):
        return obj.units.count()
    unit_count.short_description = "Nombre d'unités"


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('reference', 'building', 'unit_type', 'surface', 'status')
    list_filter = ('status', 'building__property')
    search_fields = ('reference', 'building__name', 'building__property__name')
    ordering = ('building', 'reference')
