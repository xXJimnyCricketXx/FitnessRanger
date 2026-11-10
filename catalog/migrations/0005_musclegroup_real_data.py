from django.db import migrations

FRONT_FILES = [
    "Adductor Longus and Pectineus",
    "Biceps brachii",
    "Brachialis",
    "Brachioradialis",
    "Deltoids",
    "Extensor carpi radialis",
    "External obliques",
    "Flexor carpi radialis",
    "Gastrocnemius (calf)",
    "Omohyoid",
    "Pectoralis Major",
    "Peroneus longus",
    "Rectus Abdominus",
    "Rectus Abdominus_lower",
    "Rectus femoris",
    "Sartorius",
    "Serratus Anterior",
    "Soleus",
    "Sternocleidomastoid",
    "Tensor fasciae latae",
    "Trapezius",
    "Triceps brachii, long head",
    "Triceps brachii, medial head",
    "Vastus Lateralis",
    "Vastus Medialis",
]

BACK_FILES = [
    "Adductor magnus",
    "Biceps fermoris",
    "Brachioradialis",
    "Deltoids",
    "Extensor carpi radialis",
    "External obliques",
    "Flexor carpi radialis",
    "Flexor carpi ulnaris",
    "Gastrocnemius, lateral head",
    "Gastrocnemius, medial head",
    "Gluteus maximus",
    "Gluteus medius",
    "Gracilis",
    "Infraspinatus",
    "Lattisimus dorsi",
    "Lower Trapezius",
    "Peroneus longus",
    "Rhomboid major",
    "Semitendinosus",
    "Serratus Anterior",
    "Tensor fascie latae",
    "Teres major",
    "Thoracolumbar fascia",
    "Trapezius",
    "Triceps Brachii ( long head, lateral head )",
]

# old demo MuscleGroup name -> (new name, new view) it should remap to
REMAP = {
    'Quadrizeps': ('Rectus femoris', 'front'),
    'Latissimus': ('Lattisimus dorsi', 'back'),
    'Bizeps': ('Biceps brachii', 'front'),
    'Gesäß': ('Gluteus maximus', 'back'),
}


def slugify(name):
    import re
    s = name.lower()
    s = s.replace(',', '').replace('(', '').replace(')', '')
    s = re.sub(r'\s+', '_', s.strip())
    s = re.sub(r'[^a-z0-9_]', '', s)
    return s + '.svg'


def forwards(apps, schema_editor):
    MuscleGroup = apps.get_model('catalog', 'musclegroup')
    ExerciseMuscle = apps.get_model('catalog', 'exercisemuscle')

    old_refs = list(ExerciseMuscle.objects.select_related('muscle_group').all())
    pending = [
        (ref.exercise_id, REMAP[ref.muscle_group.name][0], REMAP[ref.muscle_group.name][1], ref.role)
        for ref in old_refs
        if ref.muscle_group.name in REMAP
    ]

    MuscleGroup.objects.all().delete()

    for name in FRONT_FILES:
        MuscleGroup.objects.create(name=name, view='front', svg_file=slugify(name))
    for name in BACK_FILES:
        MuscleGroup.objects.create(name=name, view='back', svg_file=slugify(name))

    for exercise_id, name, view, role in pending:
        group = MuscleGroup.objects.filter(name=name, view=view).first()
        if group:
            ExerciseMuscle.objects.get_or_create(exercise_id=exercise_id, muscle_group=group, defaults={'role': role})


def backwards(apps, schema_editor):
    MuscleGroup = apps.get_model('catalog', 'musclegroup')
    MuscleGroup.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_musclegroup_view_svg'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
