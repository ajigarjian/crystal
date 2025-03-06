from rest_framework import serializers
from factchecker.models import DatasetCatalog

class DatasetCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetCatalog
        fields = ['dataset_id', 'title', 'description', 'organization_name', 'organization_title', 'indexed']