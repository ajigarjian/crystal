from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('factchecker', '0014_add_unique_constraint'),  # This is the new migration
    ]

    operations = [
        migrations.CreateModel(
            name='DataGovArchiveCheck',
            fields=[
                ('dataset_name', models.CharField(max_length=255, primary_key=True)),
                ('latest_version_checked', models.CharField(blank=True, max_length=10, null=True)),
                ('last_checked_at', models.DateTimeField(blank=True, null=True)),
                ('is_processed', models.BooleanField(default=False)),
                ('in_our_database', models.BooleanField(default=False)),
                ('resources_checked', models.IntegerField(default=0)),
                ('resources_available', models.IntegerField(default=0)),
                ('archive_path', models.CharField(blank=True, max_length=500, null=True)),
                ('downloaded', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('error', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'factchecker_datagovarchivecheck',
                'indexes': [
                    models.Index(fields=['is_processed'], name='idx_dgac_processed'),
                    models.Index(fields=['in_our_database'], name='idx_dgac_in_db'),
                    models.Index(fields=['last_checked_at'], name='idx_dgac_last_checked')
                ],
            },
        ),
        migrations.CreateModel(
            name='ResourceAvailabilityCheck',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('check_datetime', models.DateTimeField(auto_now_add=True)),
                ('is_available', models.BooleanField(default=False)),
                ('http_status', models.IntegerField(blank=True, null=True)),
                ('response_time_ms', models.IntegerField(blank=True, null=True)),
                ('found_in_archive', models.BooleanField(default=False)),
                ('archive_path', models.CharField(blank=True, max_length=500, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_checks', to='factchecker.datasetresource', to_field='resource_id')),
            ],
            options={
                'db_table': 'factchecker_resourceavailabilitycheck',
                'indexes': [
                    models.Index(fields=['check_datetime'], name='idx_rac_datetime'),
                    models.Index(fields=['is_available'], name='idx_rac_available'),
                    models.Index(fields=['found_in_archive'], name='idx_rac_archive')
                ],
            },
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='last_availability_check',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='is_available',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='availability_history',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='in_harvard_archive',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='harvard_archive_path',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='harvard_archive_version',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='content_hash',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='datasetresource',
            name='content_size_bytes',
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ] 