from django.db import models

class DatasetCatalog(models.Model):
    """Model to store dataset metadata from Data.gov with vector search support"""
    
    # Primary fields from the JSON data
    dataset_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    organization_title = models.CharField(max_length=500, blank=True, null=True)
    
    # Fields for search optimization
    search_text = models.TextField(blank=True, null=True)  # Combined text for basic search
    
    # Field for vector embeddings (stored as binary)
    embedding = models.BinaryField(blank=True, null=True)
    
    # Metadata fields
    indexed = models.BooleanField(default=False)  # Whether embedding has been generated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['organization_name']),
        ]
        
    def __str__(self):
        return self.title