from django.db import migrations, models
import json
from django.db.models import F, Value, TextField
from django.db.models.functions import Cast, Concat, Coalesce

def extract_json_values(apps, schema_editor):
    """Extract values from JSON fields and populate the new fields"""
    DatasetCatalog = apps.get_model('factchecker', 'DatasetCatalog')
    
    # Add new fields if there are any records
    if DatasetCatalog.objects.exists():
        # Get the first record to extract from
        DatasetCatalog.objects.all().update(
            # Date fields
            datagov_date_created=Coalesce(
                models.Func(
                    models.F('extras_json'),
                    models.Value('creation'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('issued'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('dataset-reference-date'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            ),
            
            datagov_date_issued=models.Func(
                models.F('extras_json'),
                models.Value('issued'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_date_last_modified=Coalesce(
                models.Func(
                    models.F('extras_json'),
                    models.Value('modified'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('lastUpdate'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            ),
            
            datagov_date_metadata_created=models.Func(
                models.F('extras_json'),
                models.Value('metadata-date'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_date_metadata_modified=models.Func(
                models.F('extras_json'),
                models.Value('metadata-date'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_temporal_start=models.Func(
                models.F('extras_json'),
                models.Value('temporal-extent-begin'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_temporal_end=models.Func(
                models.F('extras_json'),
                models.Value('temporal-extent-end'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_update_frequency=Coalesce(
                models.Func(
                    models.F('extras_json'),
                    models.Value('frequency-of-update'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('accrualPeriodicity'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            ),
            
            datagov_geographic_bbox=Concat(
                Value('BBOX: '),
                models.Func(
                    models.F('extras_json'),
                    models.Value('bbox-west-long'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                Value(', '),
                models.Func(
                    models.F('extras_json'),
                    models.Value('bbox-south-lat'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                Value(', '),
                models.Func(
                    models.F('extras_json'),
                    models.Value('bbox-east-long'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                Value(', '),
                models.Func(
                    models.F('extras_json'),
                    models.Value('bbox-north-lat'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            ),
            
            datagov_geographic_spatial_json=Coalesce(
                models.Func(
                    models.F('extras_json'),
                    models.Value('spatial'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('old-spatial'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            ),
            
            datagov_publisher=models.Func(
                models.F('extras_json'),
                models.Value('publisher'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_contact_email=models.Func(
                models.F('extras_json'),
                models.Value('contact-email'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_progress=models.Func(
                models.F('extras_json'),
                models.Value('progress'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_resource_type=models.Func(
                models.F('extras_json'),
                models.Value('resource-type'),
                function='jsonb_extract_path_text',
                output_field=TextField()
            ),
            
            datagov_identifier=Coalesce(
                models.Func(
                    models.F('extras_json'),
                    models.Value('identifier'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                ),
                models.Func(
                    models.F('extras_json'),
                    models.Value('guid'),
                    function='jsonb_extract_path_text',
                    output_field=TextField()
                )
            )
        )

class Migration(migrations.Migration):

    dependencies = [
        ('factchecker', '0001_initial'),
    ]

    operations = [
        # Add the fields first
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_date_created',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_date_issued',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_date_last_modified',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_date_metadata_created',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_date_metadata_modified',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_temporal_start',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_temporal_end',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_update_frequency',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_geographic_bbox',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_geographic_spatial_json',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_geographic_place_names',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_publisher',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_contact_email',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_progress',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_resource_type',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='datasetcatalog',
            name='datagov_identifier',
            field=models.TextField(blank=True, null=True),
        ),
        
        # Then run the extraction function
        migrations.RunPython(extract_json_values),
    ] 