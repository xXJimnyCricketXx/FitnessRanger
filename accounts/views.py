from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.utils import group_equipment_by_category
from plans.models import UserEquipment
from progress.models import Goal

from .forms import AccountForm, EquipmentCreateForm, GoalForm, ProfileForm, UserDataForm, UserEquipmentForm
from .models import Profile, UserData, display_name_for
from .units import Units


def build_password_change_form(user, data=None):
    form = PasswordChangeForm(user=user, data=data)
    # Changing the password is optional, so the browser must not insist on these fields.
    form.use_required_attribute = False
    form.fields['old_password'].widget.attrs.pop('autofocus', None)
    return form


def get_greeting(username):
    hour = timezone.localtime().hour
    if 5 <= hour < 11:
        return f'Guten Morgen, {username}!'
    if 11 <= hour < 18:
        return f'Guten Tag, {username}!'
    if 18 <= hour < 23:
        return f'Guten Abend, {username}!'
    return f'So spät noch wach, {username}?'


@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginPageView(TemplateView):
    template_name = 'accounts/login.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().get(request, *args, **kwargs)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/dashboard.html'
    login_url = 'login-page'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['greeting'] = get_greeting(display_name_for(self.request.user))
        return context


class MeineDatenView(LoginRequiredMixin, View):
    template_name = 'accounts/meine_daten.html'
    login_url = 'login-page'

    SECTIONS = ('personal', 'goal', 'equipment')

    def get_forms(self, request, data=None, section=None):
        # Only the submitted tab gets the POST data, the others just show what is saved.
        user_data, _ = UserData.objects.get_or_create(user=request.user)
        equipment, _ = UserEquipment.objects.get_or_create(user=request.user)
        goal = Goal.objects.filter(user=request.user).order_by('-created_at').first()
        if goal is None:
            goal = Goal(user=request.user)

        units = Units.for_user(request.user)
        user_data_form = UserDataForm(data if section == 'personal' else None, instance=user_data, prefix='userdata', units=units)
        goal_form = GoalForm(data if section == 'goal' else None, instance=goal, prefix='goal', units=units)
        equipment_form = UserEquipmentForm(data if section == 'equipment' else None, instance=equipment, prefix='equipment')
        return user_data_form, goal_form, equipment_form

    def build_context(self, user_data_form, goal_form, equipment_form, equipment_create_form=None, initial_tab=None):
        equipment_by_category = group_equipment_by_category()

        selected_equipment_ids = {str(v) for v in (equipment_form['equipment'].value() or [])}

        return {
            'user_data_form': user_data_form,
            'goal_form': goal_form,
            'units': goal_form.units,
            'equipment_form': equipment_form,
            'equipment_create_form': equipment_create_form or EquipmentCreateForm(),
            'equipment_by_category': equipment_by_category,
            'selected_equipment_ids': selected_equipment_ids,
            'initial_tab': initial_tab if initial_tab in self.SECTIONS else 'personal',
        }

    def get(self, request):
        user_data_form, goal_form, equipment_form = self.get_forms(request)
        initial_tab = request.GET.get('tab')
        return render(request, self.template_name, self.build_context(
            user_data_form, goal_form, equipment_form, initial_tab=initial_tab,
        ))

    def post(self, request):
        if request.POST.get('action') == 'add_equipment':
            return self.handle_add_equipment(request)

        section = request.POST.get('section')
        if section not in self.SECTIONS:
            return redirect('meine-daten')

        user_data_form, goal_form, equipment_form = self.get_forms(request, data=request.POST, section=section)
        form = {'personal': user_data_form, 'goal': goal_form, 'equipment': equipment_form}[section]
        if form.is_valid():
            form.save()
            messages.success(request, 'Deine Daten wurden gespeichert.')
            return redirect(f"{reverse('meine-daten')}?tab={section}")

        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return render(request, self.template_name, self.build_context(
            user_data_form, goal_form, equipment_form, initial_tab=section,
        ))

    def handle_add_equipment(self, request):
        equipment_create_form = EquipmentCreateForm(request.POST)
        if equipment_create_form.is_valid():
            equipment = equipment_create_form.save(commit=False)
            equipment.created_by = request.user
            equipment.save()
            user_equipment, _ = UserEquipment.objects.get_or_create(user=request.user)
            user_equipment.equipment.add(equipment)
            messages.success(request, f'"{equipment.name}" wurde zu deiner Ausrüstung hinzugefügt.')
            return redirect(f"{reverse('meine-daten')}?tab=equipment")

        user_data_form, goal_form, equipment_form = self.get_forms(request)
        return render(request, self.template_name, self.build_context(
            user_data_form, goal_form, equipment_form,
            equipment_create_form=equipment_create_form, initial_tab='equipment',
        ))


class ProfileView(LoginRequiredMixin, View):
    template_name = 'accounts/profil.html'
    login_url = 'login-page'

    def build_context(self, request, profile_form=None, account_form=None, password_form=None):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return {
            'profile': profile,
            'profile_form': profile_form or ProfileForm(instance=profile),
            'account_form': account_form or AccountForm(instance=request.user),
            'password_form': password_form or build_password_change_form(request.user),
        }

    def get(self, request):
        return render(request, self.template_name, self.build_context(request))

    def post(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile_form = ProfileForm(request.POST, request.FILES, instance=profile)
        # A separate instance, so rejected input doesn't show up in the header via request.user.
        account_user = User.objects.get(pk=request.user.pk)
        account_form = AccountForm(request.POST, instance=account_user)

        # Only the new password counts: browsers may autofill the current one on their own.
        wants_password_change = any(
            request.POST.get(field) for field in ('new_password1', 'new_password2')
        )
        password_form = build_password_change_form(account_user, data=request.POST) if wants_password_change else None

        valid = profile_form.is_valid() and account_form.is_valid()
        if password_form is not None:
            valid = valid and password_form.is_valid()

        if valid:
            profile_form.save()
            account_form.save()
            if password_form is not None:
                user = password_form.save()
                update_session_auth_hash(request, user)
            messages.success(request, 'Deine Profildaten wurden gespeichert.')
            return redirect('profil')

        messages.error(request, 'Bitte prüfe deine Eingaben.')
        return render(request, self.template_name, self.build_context(
            request,
            profile_form=profile_form,
            account_form=account_form,
            password_form=password_form or build_password_change_form(request.user),
        ))


class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({'detail': 'Ungueltige Anmeldedaten.'}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response({'username': user.username, 'email': user.email})


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response({'username': request.user.username, 'email': request.user.email})
