from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from .models import TrainingPlan


class PlanListView(LoginRequiredMixin, View):
    login_url = 'login-page'

    def get(self, request):
        active_filter = request.GET.get('filter', 'all')
        queryset = TrainingPlan.objects.filter(user=request.user)
        if active_filter == 'mine':
            queryset = queryset.filter(is_active=True)
        return render(request, 'catalog/list.html', {
            'page_title': 'Pläne',
            'active_filter': active_filter,
            'items': queryset,
            'card_template': 'plans/_plan_card.html',
            'create_url': '#',
        })
