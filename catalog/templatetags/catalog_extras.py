from django import template
from django.utils.safestring import mark_safe

from ..muscle_svg import render_body_map

register = template.Library()

_ICONS = {
    'freie_gewichte': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4 10h12"/><rect x="1.5" y="7" width="3" height="6" rx="1"/><rect x="15.5" y="7" width="3" height="6" rx="1"/></svg>',
    'maschine_kraft': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="4" width="14" height="12" rx="1.5"/><path d="M7 8h6M7 12h6"/></svg>',
    'maschine_cardio': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="2.5,14 8,8.5 11.5,12 17.5,5"/><polyline points="12.5,5 17.5,5 17.5,10"/></svg>',
    'zubehoer': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="10" cy="10" r="6"/><path d="M10 6v4l3 2"/></svg>',
    'balance_koordination': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2.5 14h15M10 14V6M6 6h8"/></svg>',
}


@register.simple_tag
def equipment_icon(category):
    return mark_safe(_ICONS.get(category, ''))


@register.simple_tag
def body_map(exercise, view):
    names = [em.muscle_group.name for em in exercise.exercise_muscles.all() if em.muscle_group.view == view]
    return mark_safe(render_body_map(view, names))
