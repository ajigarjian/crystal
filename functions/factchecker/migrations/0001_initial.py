from django.db import migrations, models
from django.contrib.postgres.fields import ArrayField, JSONField
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DatasetCatalog',
            fields=[
                ('dataset_id', models.CharField(max_length=255, primary_key=True)),
                ('title', models.CharField(max_length=500)),
                ('notes', models.TextField(blank=True, null=True)),
                ('organization_name', models.CharField(blank=True, max_length=255, null=True)),
                ('organization_title', models.CharField(blank=True, max_length=500, null=True)),
                ('organization_description', models.TextField(blank=True, null=True)),
                ('tags_json', models.TextField(blank=True, null=True)),
                ('search_text', models.TextField(blank=True, null=True)),
                ('embedding', models.BinaryField(blank=True, null=True)),
                ('indexed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('license_id', models.CharField(blank=True, max_length=100, null=True)),
                ('license_title', models.CharField(blank=True, max_length=255, null=True)),
                ('license_url', models.URLField(blank=True, max_length=1000, null=True)),
                ('maintainer', models.CharField(blank=True, max_length=255, null=True)),
                ('maintainer_email', models.EmailField(blank=True, max_length=255, null=True)),
                ('metadata_created', models.DateTimeField(blank=True, null=True)),
                ('metadata_modified', models.DateTimeField(blank=True, null=True)),
                ('extras_json', models.TextField(blank=True, null=True)),
                ('groups_json', models.TextField(blank=True, null=True)),
                ('image_url', models.URLField(blank=True, max_length=1000, null=True)),
            ],
            options={
                'db_table': 'factchecker_datasetcatalog',
            },
        ),
        migrations.AddIndex(
            model_name='datasetcatalog',
            index=models.Index(fields=['title'], name='factchecker_title_idx'),
        ),
        migrations.AddIndex(
            model_name='datasetcatalog',
            index=models.Index(fields=['organization_name'], name='factchecker_orgname_idx'),
        ),
    ]