from rest_framework.routers import DefaultRouter

from .views import EquipmentViewSet, ExerciseViewSet, MuscleGroupViewSet, WorkoutViewSet

router = DefaultRouter()
router.register('muscle-groups', MuscleGroupViewSet, basename='musclegroup')
router.register('equipment', EquipmentViewSet, basename='equipment')
router.register('exercises', ExerciseViewSet, basename='exercise')
router.register('workouts', WorkoutViewSet, basename='workout')

urlpatterns = router.urls
