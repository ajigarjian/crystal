from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('factchecker', '0015_add_linkrot_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='last_available_in_datagov',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='is_still_in_datagov',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='had_resources',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='has_usable_resources',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='resources_gone_bad',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='last_check_with_usable_resources',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='datagovarchivecheck',
            name='availability_history',
            field=models.JSONField(default=list, blank=True, null=True),
        ),
    ]