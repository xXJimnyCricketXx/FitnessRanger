from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import UserData, UserSettings
from progress.models import BodyMetricsEntry, Goal

TABS = ('bmi', 'kalorien', 'makros', 'einrm', 'herz', 'koerperfett')


def _age(birth_date):
    if not birth_date:
        return None
    today = timezone.localdate()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _number(value):
    return float(value) if value is not None else None


def tool_defaults(user):
    """Saved values to fill in. Everything may be missing, and nothing is ever written back."""
    user_data = UserData.objects.filter(user=user).first()
    goal = Goal.objects.filter(user=user).order_by('-created_at').first()
    latest = (
        BodyMetricsEntry.objects.filter(user=user, weight_kg__isnull=False)
        .order_by('-date')
        .values_list('weight_kg', flat=True)
        .first()
    )
    weight = latest if latest is not None else (user_data.starting_weight_kg if user_data else None)
    return {
        'weight_kg': _number(weight),
        'height_cm': user_data.height_cm if user_data else None,
        'age': _age(user_data.birth_date) if user_data else None,
        'gender': user_data.gender if user_data else '',
        'activity': user_data.activity_level if user_data else '',
        'goal': goal.goal_type if goal else '',
    }


class ToolsView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/tools.html'
    login_url = 'login-page'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_settings = UserSettings.objects.filter(user=self.request.user).first()
        tab = self.request.GET.get('tab')
        context.update({
            'initial_tab': tab if tab in TABS else TABS[0],
            'defaults': tool_defaults(self.request.user),
            'weight_unit': user_settings.weight_unit if user_settings else UserSettings.WeightUnit.KG,
            'length_unit': user_settings.length_unit if user_settings else UserSettings.LengthUnit.CM,
            'activity_choices': UserData.ActivityLevel.choices,
            'goal_choices': Goal.GoalType.choices,
        })
        return context
