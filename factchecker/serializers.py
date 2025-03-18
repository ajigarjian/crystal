from rest_framework import serializers
from factchecker.models import DatasetCatalog

class DatasetCatalogSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    
    class Meta:
        model = DatasetCatalog
        fields = [
            'dataset_id', 
            'title', 
            'notes', 
            'organization_name', 
            'organization_title', 
            'image_url', 
            'tags'
        ]
    
    def get_tags(self, obj):
        """Get tags as a list of strings"""
        if not obj.tags_json:
            return []
        try:
            return obj.tags
        except:
            return []