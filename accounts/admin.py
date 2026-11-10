from django.contrib import admin

from .models import Profile, SystemSettings, UserData, UserSettings


@admin.register(UserData)
class UserDataAdmin(admin.ModelAdmin):
    list_display = ('user', 'birth_date', 'gender', 'height_cm', 'starting_weight_kg', 'fitness_level', 'activity_level')
    list_filter = ('gender', 'fitness_level', 'activity_level')
    search_fields = ('user__username',)


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ('auto_enabled', 'interval_hours', 'keep_count', 'last_auto_at')


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'language', 'weight_unit', 'length_unit')
    search_fields = ('user__username',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'avatar')
    search_fields = ('user__username',)
