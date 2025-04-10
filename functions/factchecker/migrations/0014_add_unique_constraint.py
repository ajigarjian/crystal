from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('factchecker', '0003_add_datagov_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasetresource',
            name='resource_id',
            field=models.CharField(max_length=255, unique=True),
        ),
    ] 