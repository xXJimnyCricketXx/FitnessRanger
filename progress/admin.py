from django.contrib import admin

from .models import BodyMetricsEntry, Goal


@admin.register(BodyMetricsEntry)
class BodyMetricsEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'weight_kg', 'body_fat_pct', 'source')
    list_filter = ('source', 'date')
    search_fields = ('user__username',)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'goal_type', 'target_weight_kg', 'target_date')
    list_filter = ('goal_type',)
    search_fields = ('user__username',)
