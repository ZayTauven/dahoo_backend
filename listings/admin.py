
# listings/admin.py
from django.contrib import admin
from .models import Listing, Prospect, ProspectInterest

admin.site.register(Listing)
admin.site.register(Prospect)
admin.site.register(ProspectInterest)
