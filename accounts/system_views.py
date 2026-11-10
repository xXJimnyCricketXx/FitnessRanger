import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from .backup import (
    BackupError,
    backup_dir,
    build_user_backup,
    create_backup,
    delete_backup,
    list_backups,
    resolve_backup,
    restore_backup,
)
from .forms import ManagedUserForm, SystemSettingsForm, UserSettingsForm
from .maintenance import delete_training_data, delete_user_with_files, reset_installation
from .models import SystemSettings, UserSettings, display_name_for

CONFIRM_RESTORE = 'WIEDERHERSTELLEN'
CONFIRM_DELETE_DATA = 'LÖSCHEN'
CONFIRM_RESET = 'ZURÜCKSETZEN'


def system_tab_url():
    return f"{reverse('einstellungen')}?tab=system"


class SettingsView(LoginRequiredMixin, View):
    template_name = 'accounts/einstellungen.html'
    login_url = 'login-page'

    def render_page(self, request, form=None, tab='general', system_form=None):
        user_settings, _ = UserSettings.objects.get_or_create(user=request.user)
        tabs = ('general', 'backups', 'system') if request.user.is_superuser else ('general', 'backups')
        context = {
            'form': form or UserSettingsForm(instance=user_settings),
            'initial_tab': tab if tab in tabs else 'general',
        }
        if request.user.is_superuser:
            system_settings = SystemSettings.load()
            users = get_user_model().objects.select_related('profile').order_by('username')
            context.update({
                'system_settings': system_settings,
                'system_form': system_form or SystemSettingsForm(instance=system_settings),
                'backups': list_backups(),
                'managed_users': [(user, display_name_for(user)) for user in users],
                'confirm_restore': CONFIRM_RESTORE,
                'confirm_delete_data': CONFIRM_DELETE_DATA,
                'confirm_reset': CONFIRM_RESET,
            })
        return render(request, self.template_name, context)

    def get(self, request):
        return self.render_page(request, tab=request.GET.get('tab', 'general'))

    def post(self, request):
        user_settings, _ = UserSettings.objects.get_or_create(user=request.user)
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Deine Einstellungen wurden gespeichert.')
            return redirect('einstellungen')
        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return self.render_page(request, form=form)


class UserBackupView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        name = slugify(request.user.username) or 'konto'
        filename = f'fitnessranger-backup-{name}-{timezone.localdate():%Y-%m-%d}.zip'
        response = FileResponse(
            build_user_backup(request.user), as_attachment=True, filename=filename, content_type='application/zip',
        )
        response['Cache-Control'] = 'no-store'
        return response


class SuperuserRequiredMixin(LoginRequiredMixin):
    login_url = 'login-page'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def confirmed(request, word):
    """Dangerous actions need the exact word and the admin's own password."""
    if request.POST.get('confirmation', '').strip() != word:
        messages.error(request, f'Bitte gib zur Bestätigung genau „{word}“ ein.')
        return False
    if not request.user.check_password(request.POST.get('password', '')):
        messages.error(request, 'Das Passwort ist nicht korrekt.')
        return False
    return True


class SystemSettingsView(SuperuserRequiredMixin, SettingsView):
    def get(self, request):
        return redirect(system_tab_url())

    def post(self, request):
        form = SystemSettingsForm(request.POST, instance=SystemSettings.load())
        if form.is_valid():
            form.save()
            messages.success(request, 'Die Backup-Einstellungen wurden gespeichert.')
            return redirect(system_tab_url())
        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return self.render_page(request, tab='system', system_form=form)


class BackupCreateView(SuperuserRequiredMixin, View):
    def post(self, request):
        try:
            create_backup('manual')
        except (OSError, DatabaseError):
            messages.error(request, 'Das Backup konnte nicht erstellt werden.')
        else:
            messages.success(request, 'Das Backup wurde erstellt.')
        return redirect(system_tab_url())


class BackupDownloadView(SuperuserRequiredMixin, View):
    def get(self, request, name):
        try:
            path = resolve_backup(name)
        except BackupError as error:
            raise Http404 from error
        response = FileResponse(open(path, 'rb'), as_attachment=True, filename=name, content_type='application/zip')
        response['Cache-Control'] = 'no-store'
        return response


class BackupDeleteView(SuperuserRequiredMixin, View):
    def post(self, request, name):
        try:
            delete_backup(name)
        except BackupError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Das Backup wurde gelöscht.')
        return redirect(system_tab_url())


class BackupRestoreView(SuperuserRequiredMixin, View):
    def post(self, request):
        if not confirmed(request, CONFIRM_RESTORE):
            return redirect(system_tab_url())

        upload = request.FILES.get('upload')
        name = request.POST.get('source', '')
        if bool(upload) == bool(name):
            messages.error(request, 'Bitte wähle entweder ein vorhandenes Backup oder eine Datei aus.')
            return redirect(system_tab_url())

        uploaded_path = None
        try:
            if upload:
                uploaded_path = backup_dir() / f'.upload-{uuid.uuid4().hex}.tmp'
                with open(uploaded_path, 'wb') as target:
                    for chunk in upload.chunks():
                        target.write(chunk)
                path = uploaded_path
            else:
                path = resolve_backup(name)
            restore_backup(path)
        except BackupError as error:
            messages.error(request, str(error))
            return redirect(system_tab_url())
        finally:
            if uploaded_path:
                uploaded_path.unlink(missing_ok=True)

        # The accounts and sessions now come from the backup, so everyone logs in again.
        logout(request)
        messages.success(request, 'Das Backup wurde wiederhergestellt. Bitte melde dich neu an.')
        return redirect('login-page')


class UserCreateView(SuperuserRequiredMixin, View):
    template_name = 'accounts/benutzer_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ManagedUserForm(acting_user=request.user)})

    def post(self, request):
        form = ManagedUserForm(request.POST, acting_user=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'„{user.username}“ wurde angelegt.')
            return redirect(system_tab_url())
        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return render(request, self.template_name, {'form': form})


class UserEditView(SuperuserRequiredMixin, View):
    template_name = 'accounts/benutzer_form.html'

    def get_user(self, pk):
        return get_object_or_404(get_user_model(), pk=pk)

    def get(self, request, pk):
        target = self.get_user(pk)
        return render(request, self.template_name, {
            'form': ManagedUserForm(instance=target, acting_user=request.user),
            'target': target,
        })

    def post(self, request, pk):
        target = self.get_user(pk)
        form = ManagedUserForm(request.POST, instance=target, acting_user=request.user)
        if form.is_valid():
            user = form.save()
            if user.pk == request.user.pk:
                update_session_auth_hash(request, user)
            messages.success(request, f'„{user.username}“ wurde gespeichert.')
            return redirect(system_tab_url())
        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return render(request, self.template_name, {
            'form': form,
            # A fresh copy, because the form has already applied the rejected input to its instance.
            'target': self.get_user(pk),
        })


class UserDeleteView(SuperuserRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(get_user_model(), pk=pk)
        edit_url = reverse('benutzer-bearbeiten', args=[target.pk])
        if target.pk == request.user.pk:
            messages.error(request, 'Du kannst dein eigenes Konto hier nicht löschen.')
            return redirect(edit_url)
        if request.POST.get('confirmation', '').strip() != target.username:
            messages.error(request, f'Bitte gib zur Bestätigung genau „{target.username}“ ein.')
            return redirect(edit_url)
        username = target.username
        delete_user_with_files(target)
        messages.success(request, f'„{username}“ wurde gelöscht.')
        return redirect(system_tab_url())


class DangerDeleteDataView(SuperuserRequiredMixin, View):
    def post(self, request):
        if confirmed(request, CONFIRM_DELETE_DATA):
            try:
                create_backup('safety')
            except (OSError, DatabaseError):
                messages.error(request, 'Die Sicherheitskopie ist fehlgeschlagen, deshalb wurde nichts gelöscht.')
            else:
                delete_training_data()
                messages.success(request, 'Alle Trainings- und Fortschrittsdaten wurden gelöscht. Vorher wurde eine Sicherheitskopie erstellt.')
        return redirect(system_tab_url())


class DangerResetView(SuperuserRequiredMixin, View):
    def post(self, request):
        if confirmed(request, CONFIRM_RESET):
            try:
                create_backup('safety')
            except (OSError, DatabaseError):
                messages.error(request, 'Die Sicherheitskopie ist fehlgeschlagen, deshalb wurde nichts gelöscht.')
            else:
                reset_installation(request.user, request.session.session_key)
                messages.success(request, 'Die Installation wurde zurückgesetzt. Vorher wurde eine Sicherheitskopie erstellt.')
        return redirect(system_tab_url())
