from django.contrib import admin

from .models import Profile, UserData


@admin.register(UserData)
class UserDataAdmin(admin.ModelAdmin):
    list_display = ('user', 'birth_date', 'gender', 'height_cm', 'starting_weight_kg', 'fitness_level', 'activity_level')
    list_filter = ('gender', 'fitness_level', 'activity_level')
    search_fields = ('user__username',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'avatar')
    search_fields = ('user__username',)
