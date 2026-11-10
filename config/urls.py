"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import posixpath

from django.conf import settings
from django.contrib import admin
from django.http import Http404
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.generic import RedirectView

from accounts.system_views import (
    BackupCreateView,
    BackupDeleteView,
    BackupDownloadView,
    BackupRestoreView,
    DangerDeleteDataView,
    DangerResetView,
    SettingsView,
    SystemSettingsView,
    UserBackupView,
    UserCreateView,
    UserDeleteView,
    UserEditView,
)
from accounts.views import DashboardView, LoginPageView, MeineDatenView, ProfileView
from catalog.views import ExerciseCreateView, ExerciseListView, WorkoutListView
from plans.views import PlanListView
from progress.models import PRIVATE_MEDIA_PREFIX
from progress.views import (
    EntryDeleteView, EntryEditView, ImportView, MeasurementCreateView, PhotoDeleteView, PhotoFileView,
    PhotoUploadView, ProgressView, StatisticsView, WeightCreateView,
)
from tools.views import ToolsView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('catalog.urls')),
    path('login/', LoginPageView.as_view(), name='login-page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('meine-daten/', MeineDatenView.as_view(), name='meine-daten'),
    path('einstellungen/', SettingsView.as_view(), name='einstellungen'),
    path('einstellungen/backup/meine-daten/', UserBackupView.as_view(), name='backup-meine-daten'),
    path('einstellungen/system/', SystemSettingsView.as_view(), name='system-einstellungen'),
    path('einstellungen/system/backups/erstellen/', BackupCreateView.as_view(), name='backup-erstellen'),
    path('einstellungen/system/backups/wiederherstellen/', BackupRestoreView.as_view(), name='backup-wiederherstellen'),
    path('einstellungen/system/backups/<str:name>/download/', BackupDownloadView.as_view(), name='backup-download'),
    path('einstellungen/system/backups/<str:name>/loeschen/', BackupDeleteView.as_view(), name='backup-loeschen'),
    path('einstellungen/system/benutzer/neu/', UserCreateView.as_view(), name='benutzer-neu'),
    path('einstellungen/system/benutzer/<int:pk>/', UserEditView.as_view(), name='benutzer-bearbeiten'),
    path('einstellungen/system/benutzer/<int:pk>/loeschen/', UserDeleteView.as_view(), name='benutzer-loeschen'),
    path('einstellungen/system/danger/daten/', DangerDeleteDataView.as_view(), name='danger-daten'),
    path('einstellungen/system/danger/reset/', DangerResetView.as_view(), name='danger-reset'),
    path('profil/', ProfileView.as_view(), name='profil'),
    path('uebungen/', ExerciseListView.as_view(), name='uebungen-liste'),
    path('uebungen/neu/', ExerciseCreateView.as_view(), name='uebung-neu'),
    path('workouts/', WorkoutListView.as_view(), name='workouts-liste'),
    path('plaene/', PlanListView.as_view(), name='plaene-liste'),
    path('fortschritt/', ProgressView.as_view(), name='fortschritt'),
    path('fortschritt/gewicht/', WeightCreateView.as_view(), name='fortschritt-gewicht'),
    path('fortschritt/masse/', MeasurementCreateView.as_view(), name='fortschritt-masse'),
    path('fortschritt/import/', ImportView.as_view(), name='fortschritt-import'),
    path('statistik/', StatisticsView.as_view(), name='statistik'),
    path('fortschritt/fotos/neu/', PhotoUploadView.as_view(), name='fortschritt-fotos-neu'),
    path('fortschritt/fotos/<int:pk>/', PhotoFileView.as_view(), name='fortschritt-foto'),
    path('fortschritt/fotos/<int:pk>/loeschen/', PhotoDeleteView.as_view(), name='fortschritt-foto-loeschen'),
    path('fortschritt/<int:pk>/bearbeiten/', EntryEditView.as_view(), name='fortschritt-bearbeiten'),
    path('fortschritt/<int:pk>/loeschen/', EntryDeleteView.as_view(), name='fortschritt-loeschen'),
    path('tools/', ToolsView.as_view(), name='tools'),
    path('', RedirectView.as_view(pattern_name='dashboard', permanent=False)),
]

def public_media(request, path):
    """Serves uploads like avatars, but never the private folder with progress photos."""
    clean = posixpath.normpath(path.replace('\\', '/')).lstrip('/').lower()
    if clean == PRIVATE_MEDIA_PREFIX.rstrip('/') or clean.startswith(PRIVATE_MEDIA_PREFIX):
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    urlpatterns += [re_path(r'^media/(?P<path>.*)$', public_media)]
