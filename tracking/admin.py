from django.contrib import admin

from .models import TrackingEntry


@admin.register(TrackingEntry)
class TrackingEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'exercise', 'weight_kg', 'completed')
    list_filter = ('completed', 'date')
    search_fields = ('user__username', 'exercise__name')
