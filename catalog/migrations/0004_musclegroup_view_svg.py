from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_traininggoal_exercise_image_exercise_goals'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='musclegroup',
            name='region',
        ),
        migrations.AlterField(
            model_name='musclegroup',
            name='name',
            field=models.CharField(max_length=100),
        ),
        migrations.AddField(
            model_name='musclegroup',
            name='view',
            field=models.CharField(choices=[('front', 'Vorderseite'), ('back', 'Rückseite')], default='front', max_length=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='musclegroup',
            name='svg_file',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='musclegroup',
            options={'ordering': ['view', 'name']},
        ),
        migrations.AlterUniqueTogether(
            name='musclegroup',
            unique_together={('name', 'view')},
        ),
    ]
