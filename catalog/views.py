from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from rest_framework import viewsets

from .forms import ExerciseForm
from .models import Equipment, Exercise, ExerciseMuscle, MuscleGroup, Workout
from .serializers import EquipmentSerializer, ExerciseSerializer, MuscleGroupSerializer, WorkoutSerializer
from .utils import group_equipment_by_category, group_muscles_by_view


class MuscleGroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MuscleGroup.objects.all()
    serializer_class = MuscleGroupSerializer


class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all().select_related('created_by__profile')
    serializer_class = EquipmentSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ExerciseViewSet(viewsets.ModelViewSet):
    queryset = Exercise.objects.all().select_related('created_by__profile').prefetch_related('equipment', 'exercise_muscles__muscle_group')
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
    queryset = Workout.objects.all().select_related('created_by__profile').prefetch_related('workout_exercises__exercise')
    serializer_class = WorkoutSerializer


class ExerciseListView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        active_filter = request.GET.get('filter', 'all')
        queryset = Exercise.objects.all().prefetch_related('equipment', 'exercise_muscles__muscle_group')
        if active_filter == 'mine':
            queryset = queryset.filter(created_by=request.user)
        return render(request, 'catalog/list.html', {
            'page_title': 'Übungen',
            'active_filter': active_filter,
            'items': queryset,
            'card_template': 'catalog/_exercise_card.html',
            'create_url': reverse('uebung-neu'),
        })


class WorkoutListView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        active_filter = request.GET.get('filter', 'all')
        queryset = Workout.objects.all().prefetch_related('workout_exercises')
        if active_filter == 'mine':
            queryset = queryset.filter(created_by=request.user)
        return render(request, 'catalog/list.html', {
            'page_title': 'Workouts',
            'active_filter': active_filter,
            'items': queryset,
            'card_template': 'catalog/_workout_card.html',
            'create_url': '#',
        })


class ExerciseCreateView(LoginRequiredMixin, View):
    login_url = 'login-page'
    template_name = 'catalog/exercise_form.html'

    def build_context(self, form=None, selected_equipment_ids=None, selected_primary_ids=None, selected_secondary_ids=None):
        return {
            'form': form or ExerciseForm(),
            'equipment_by_category': group_equipment_by_category(),
            'muscles_by_view': group_muscles_by_view(),
            'selected_equipment_ids': selected_equipment_ids or set(),
            'selected_primary_ids': selected_primary_ids or set(),
            'selected_secondary_ids': selected_secondary_ids or set(),
        }

    def get(self, request):
        return render(request, self.template_name, self.build_context())

    def post(self, request):
        form = ExerciseForm(request.POST, request.FILES)
        equipment_ids = request.POST.getlist('equipment')
        primary_ids = request.POST.getlist('primary_muscles')
        secondary_ids = request.POST.getlist('secondary_muscles')

        if form.is_valid():
            exercise = form.save(commit=False)
            exercise.created_by = request.user
            exercise.save()
            form.save_m2m()
            exercise.equipment.set(equipment_ids)
            for muscle_id in primary_ids:
                ExerciseMuscle.objects.create(exercise=exercise, muscle_group_id=muscle_id, role=ExerciseMuscle.Role.PRIMARY)
            for muscle_id in secondary_ids:
                if muscle_id not in primary_ids:
                    ExerciseMuscle.objects.create(exercise=exercise, muscle_group_id=muscle_id, role=ExerciseMuscle.Role.SECONDARY)
            messages.success(request, f'"{exercise.name}" wurde angelegt.')
            return redirect('uebungen-liste')

        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return render(request, self.template_name, self.build_context(
            form=form,
            selected_equipment_ids=set(equipment_ids),
            selected_primary_ids=set(primary_ids),
            selected_secondary_ids=set(secondary_ids),
        ))
