from django.contrib import admin

from .models import TrainingPlan, TrainingPlanEntry, UserEquipment


class TrainingPlanEntryInline(admin.TabularInline):
    model = TrainingPlanEntry
    extra = 1


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'user__username')
    inlines = [TrainingPlanEntryInline]


@admin.register(UserEquipment)
class UserEquipmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'studio_access')
    filter_horizontal = ('equipment',)
