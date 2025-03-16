from django.db import models
import json
from django.utils import timezone

class DatasetCatalog(models.Model):
    """Model to store dataset metadata from Data.gov with vector search support"""
    
    # Primary fields from the JSON data
    dataset_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    organization_title = models.CharField(max_length=500, blank=True, null=True)
    
    # New field for tags (stored as JSON string)
    tags_json = models.TextField(blank=True, null=True)
    
    # Fields for search optimization
    search_text = models.TextField(blank=True, null=True)  # Combined text for basic search
    
    # Field for vector embeddings (stored as binary)
    embedding = models.BinaryField(blank=True, null=True)
    
    # Metadata fields
    indexed = models.BooleanField(default=False)  # Whether embedding has been generated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional fields for DatasetCatalog
    license_id = models.CharField(max_length=100, blank=True, null=True)
    license_title = models.CharField(max_length=255, blank=True, null=True)
    license_url = models.URLField(max_length=1000, blank=True, null=True)
    maintainer = models.CharField(max_length=255, blank=True, null=True)
    maintainer_email = models.EmailField(max_length=255, blank=True, null=True)
    metadata_created = models.DateTimeField(blank=True, null=True)
    metadata_modified = models.DateTimeField(blank=True, null=True)
    extras_json = models.TextField(blank=True, null=True)  # Store extras as JSON
    groups_json = models.TextField(blank=True, null=True)  # Store groups as JSON
    
    # Add this new field
    notes = models.TextField(blank=True, null=True)
    
    # New field for image URL
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['organization_name']),
        ]
    
    @property
    def tags(self):
        """Get tags as a list"""
        if not self.tags_json:
            return []
        try:
            return json.loads(self.tags_json)
        except:
            return []
    
    @tags.setter
    def tags(self, value):
        """Set tags from a list"""
        if value is None:
            self.tags_json = None
        else:
            self.tags_json = json.dumps(value)
    
    @property
    def extras(self):
        """Get extras as a dictionary"""
        if not self.extras_json:
            return {}
        try:
            return json.loads(self.extras_json)
        except:
            return {}
    
    @extras.setter
    def extras(self, value):
        """Set extras from a dictionary"""
        if value is None:
            self.extras_json = None
        else:
            self.extras_json = json.dumps(value)
    
    @property
    def groups(self):
        """Get groups as a list"""
        if not self.groups_json:
            return []
        try:
            return json.loads(self.groups_json)
        except:
            return []
    
    @groups.setter
    def groups(self, value):
        """Set groups from a list"""
        if value is None:
            self.groups_json = None
        else:
            self.groups_json = json.dumps(value)
    
    def __str__(self):
        return self.title

class DatasetResource(models.Model):
    """Model to store information about individual resources (data files) within datasets"""
    
    # Unique identifier for the resource
    resource_id = models.CharField(max_length=255, primary_key=True)
    
    # Foreign key to the dataset
    dataset = models.ForeignKey(DatasetCatalog, on_delete=models.CASCADE, related_name='resources')
    
    # Resource metadata
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    format = models.CharField(max_length=50, blank=True, null=True)
    url = models.URLField(max_length=1000)
    size = models.BigIntegerField(blank=True, null=True)  # Size in bytes
    created = models.DateTimeField(blank=True, null=True)
    last_modified = models.DateTimeField(blank=True, null=True)
    
    # Additional fields for DatasetResource
    mimetype = models.CharField(max_length=255, blank=True, null=True)
    mimetype_inner = models.CharField(max_length=255, blank=True, null=True)
    position = models.IntegerField(blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    hash = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['format']),
        ]
    
    def __str__(self):
        return self.name

class WaitlistEntry(models.Model):
    first_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.email}"