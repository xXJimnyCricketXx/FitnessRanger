from .models import Equipment, MuscleGroup


def group_equipment_by_category():
    groups = []
    for value, label in Equipment.Category.choices:
        items = Equipment.objects.filter(category=value)
        if items.exists():
            groups.append((label, items))
    return groups


def group_muscles_by_view():
    groups = []
    for value, label in MuscleGroup.View.choices:
        items = MuscleGroup.objects.filter(view=value)
        if items.exists():
            groups.append((label, items))
    return groups
