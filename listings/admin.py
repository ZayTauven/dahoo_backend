
# listings/admin.py
from django.contrib import admin
from .models import Listing, ListingPhoto, Prospect, ProspectInterest


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0
    fields = ("image", "alt", "position")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "listing_type", "price", "status", "published_at")
    list_filter = ("status", "listing_type")
    search_fields = ("title",)
    inlines = [ListingPhotoInline]


admin.site.register(Prospect)
admin.site.register(ProspectInterest)
