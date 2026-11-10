from django.contrib import admin

from .models import Equipment, Exercise, ExerciseMuscle, MuscleGroup, TrainingGoal, Workout, WorkoutExercise


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'view', 'svg_file')
    list_filter = ('view',)
    search_fields = ('name',)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_bodyweight', 'created_by')
    list_filter = ('category', 'is_bodyweight')
    search_fields = ('name',)


@admin.register(TrainingGoal)
class TrainingGoalAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class ExerciseMuscleInline(admin.TabularInline):
    model = ExerciseMuscle
    extra = 1


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ('name', 'difficulty', 'force', 'mechanic', 'created_by', 'created_at')
    list_filter = ('difficulty', 'force', 'mechanic', 'grip')
    search_fields = ('name',)
    inlines = [ExerciseMuscleInline]
    exclude = ('muscle_groups',)


class WorkoutExerciseInline(admin.TabularInline):
    model = WorkoutExercise
    extra = 1


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name',)
    inlines = [WorkoutExerciseInline]
