from rest_framework import viewsets

from .models import Equipment, Exercise, MuscleGroup, Workout
from .serializers import EquipmentSerializer, ExerciseSerializer, MuscleGroupSerializer, WorkoutSerializer


class MuscleGroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MuscleGroup.objects.all()
    serializer_class = MuscleGroupSerializer


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ExerciseViewSet(viewsets.ModelViewSet):
    queryset = Exercise.objects.all().prefetch_related('equipment', 'exercise_muscles__muscle_group')
    serializer_class = ExerciseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        muscle_id = self.request.query_params.get('muscle')
        equipment_id = self.request.query_params.get('equipment')
        if muscle_id:
            queryset = queryset.filter(exercise_muscles__muscle_group_id=muscle_id)
        if equipment_id:
            queryset = queryset.filter(equipment__id=equipment_id)
        return queryset.distinct()


class WorkoutViewSet(viewsets.ModelViewSet):
    queryset = Workout.objects.all().prefetch_related('workout_exercises__exercise')
    serializer_class = WorkoutSerializer
