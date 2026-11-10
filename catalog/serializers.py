from rest_framework import serializers

from accounts.models import display_name_for

from .models import Equipment, Exercise, ExerciseMuscle, MuscleGroup, Workout, WorkoutExercise


class CreatedByField(serializers.ReadOnlyField):
    def to_representation(self, user):
        return display_name_for(user)


class MuscleGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = MuscleGroup
        fields = ['id', 'name', 'view', 'svg_file']


class EquipmentSerializer(serializers.ModelSerializer):
    created_by = CreatedByField()

    class Meta:
        model = Equipment
        fields = ['id', 'name', 'category', 'is_bodyweight', 'created_by']


class ExerciseMuscleSerializer(serializers.ModelSerializer):
    muscle_group = serializers.PrimaryKeyRelatedField(queryset=MuscleGroup.objects.all())
    muscle_group_name = serializers.ReadOnlyField(source='muscle_group.name')

    class Meta:
        model = ExerciseMuscle
        fields = ['id', 'muscle_group', 'muscle_group_name', 'role']


class ExerciseSerializer(serializers.ModelSerializer):
    created_by = CreatedByField()
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), many=True, required=False)
    exercise_muscles = ExerciseMuscleSerializer(many=True, required=False)

    class Meta:
        model = Exercise
        fields = [
            'id', 'name', 'equipment', 'instructions', 'video_url',
            'difficulty', 'force', 'mechanic', 'grip',
            'exercise_muscles', 'created_by', 'created_at',
        ]

    def create(self, validated_data):
        muscles_data = validated_data.pop('exercise_muscles', [])
        equipment = validated_data.pop('equipment', [])
        validated_data['created_by'] = self.context['request'].user
        exercise = Exercise.objects.create(**validated_data)
        exercise.equipment.set(equipment)
        for muscle_data in muscles_data:
            ExerciseMuscle.objects.create(exercise=exercise, **muscle_data)
        return exercise

    def update(self, instance, validated_data):
        muscles_data = validated_data.pop('exercise_muscles', None)
        equipment = validated_data.pop('equipment', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if equipment is not None:
            instance.equipment.set(equipment)
        if muscles_data is not None:
            instance.exercise_muscles.all().delete()
            for muscle_data in muscles_data:
                ExerciseMuscle.objects.create(exercise=instance, **muscle_data)
        return instance


class WorkoutExerciseSerializer(serializers.ModelSerializer):
    exercise_name = serializers.ReadOnlyField(source='exercise.name')

    class Meta:
        model = WorkoutExercise
        fields = ['id', 'exercise', 'exercise_name', 'order', 'sets', 'reps', 'notes']


class WorkoutSerializer(serializers.ModelSerializer):
    created_by = CreatedByField()
    workout_exercises = WorkoutExerciseSerializer(many=True, required=False)

    class Meta:
        model = Workout
        fields = ['id', 'name', 'description', 'workout_exercises', 'created_by', 'created_at']

    def create(self, validated_data):
        exercises_data = validated_data.pop('workout_exercises', [])
        validated_data['created_by'] = self.context['request'].user
        workout = Workout.objects.create(**validated_data)
        for exercise_data in exercises_data:
            WorkoutExercise.objects.create(workout=workout, **exercise_data)
        return workout

    def update(self, instance, validated_data):
        exercises_data = validated_data.pop('workout_exercises', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if exercises_data is not None:
            instance.workout_exercises.all().delete()
            for exercise_data in exercises_data:
                WorkoutExercise.objects.create(workout=instance, **exercise_data)
        return instance
