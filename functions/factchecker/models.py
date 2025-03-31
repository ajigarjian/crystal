from django.db import models
import json
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField

class DatasetCatalog(models.Model):
    """Model to store dataset metadata from Data.gov with vector search support"""
    
    # Primary fields from the JSON data
    dataset_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=500)
    notes = models.TextField(blank=True, null=True)
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    organization_title = models.CharField(max_length=500, blank=True, null=True)
    organization_description = models.TextField(blank=True, null=True)
    
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
    
    # New field for image URL
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    
    class Meta:
        app_label = 'factchecker'
        db_table = 'factchecker_datasetcatalog'
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

    # New fields for cached dataset resources
    is_cached = models.BooleanField(default=False)
    cache_uri = models.CharField(max_length=255, blank=True, null=True)
    resource_download_error = models.BooleanField(default=False)
    last_cached = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        app_label = 'factchecker'
        db_table = 'factchecker_datasetresource'
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

# CENSUS API MODELS

class CensusDataset(models.Model):
    """Model to store Census API dataset metadata"""
    
    # Unique identifier - combination of vintage and dataset path
    id = models.AutoField(primary_key=True)
    vintage = models.IntegerField()  # Year (e.g., 2020)
    dataset_path = models.CharField(max_length=255)  # e.g., "acs/acs5"
    
    # Basic metadata
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    
    # Type of dataset
    is_aggregate = models.BooleanField(default=False)
    is_microdata = models.BooleanField(default=False)
    
    # Temporal coverage
    reference_period = models.CharField(max_length=50, blank=True, null=True)  # e.g., "2016-2020"
    modified_date = models.DateTimeField(blank=True, null=True)
    
    # API endpoint
    api_endpoint = models.URLField(max_length=500)
    
    # Fields for search optimization
    embedding = models.BinaryField(blank=True, null=True)  # For vector search
    
    # Metadata fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('vintage', 'dataset_path')
        indexes = [
            models.Index(fields=['vintage']),
            models.Index(fields=['dataset_path']),
        ]
    
    def __str__(self):
        return f"{self.vintage} {self.title}"

class CensusVariable(models.Model):
    """Model to store Census variables within datasets"""
    
    # Unique identifier
    id = models.AutoField(primary_key=True)
    
    # Foreign key to the dataset
    dataset = models.ForeignKey(CensusDataset, on_delete=models.CASCADE, related_name='variables')
    
    # Variable details
    variable_name = models.CharField(max_length=100)  # e.g., "B01001_001E"
    label = models.TextField()  # e.g., "Estimate!!Total:"
    concept = models.CharField(max_length=500, blank=True, null=True)  # e.g., "SEX BY AGE"
    group_name = models.CharField(max_length=100, blank=True, null=True)  # e.g., "B01001"
    predicate_type = models.CharField(max_length=50, blank=True, null=True)  # e.g., "int"
    
    # Fields for search optimization
    embedding = models.BinaryField(blank=True, null=True)  # For semantic search
    
    class Meta:
        unique_together = ('dataset', 'variable_name')
        indexes = [
            models.Index(fields=['variable_name']),
            models.Index(fields=['group_name']),
            models.Index(fields=['concept']),
        ]
    
    def __str__(self):
        return f"{self.variable_name} - {self.label}"

class CensusGroup(models.Model):
    """Model to store Census groups (tables) within datasets"""
    
    # Unique identifier
    id = models.AutoField(primary_key=True)
    
    # Foreign key to the dataset
    dataset = models.ForeignKey(CensusDataset, on_delete=models.CASCADE, related_name='groups')
    
    # Group details
    name = models.CharField(max_length=100)  # e.g., "B01001"
    description = models.TextField(blank=True, null=True)
    variables_url = models.URLField(max_length=500, blank=True, null=True)  # Link to variables data
    
    # Fields for search optimization
    embedding = models.BinaryField(blank=True, null=True)  # For semantic search
    
    class Meta:
        unique_together = ('dataset', 'name')
        indexes = [
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.description}"

class CensusGeography(models.Model):
    """Model to store Census geographic levels available for datasets"""
    
    # Unique identifier
    id = models.AutoField(primary_key=True)
    
    # Foreign key to the dataset
    dataset = models.ForeignKey(CensusDataset, on_delete=models.CASCADE, related_name='geographies')
    
    # Geography details
    name = models.CharField(max_length=100)  # e.g., "state", "county"
    geo_level_display = models.CharField(max_length=10, blank=True, null=True)  # e.g., "040"
    reference_date = models.DateField(blank=True, null=True)
    
    # Required and wildcard geographies (stored as JSON)
    requires_json = models.TextField(blank=True, null=True)  # e.g., ["state"]
    wildcard_json = models.TextField(blank=True, null=True)  # e.g., ["state"]
    
    class Meta:
        unique_together = ('dataset', 'name')
        indexes = [
            models.Index(fields=['name']),
        ]
    
    @property
    def requires(self):
        """Get requires as a list"""
        if not self.requires_json:
            return []
        try:
            return json.loads(self.requires_json)
        except:
            return []
    
    @requires.setter
    def requires(self, value):
        """Set requires from a list"""
        if value is None:
            self.requires_json = None
        else:
            self.requires_json = json.dumps(value)
    
    @property
    def wildcard(self):
        """Get wildcard as a list"""
        if not self.wildcard_json:
            return []
        try:
            return json.loads(self.wildcard_json)
        except:
            return []
    
    @wildcard.setter
    def wildcard(self, value):
        """Set wildcard from a list"""
        if value is None:
            self.wildcard_json = None
        else:
            self.wildcard_json = json.dumps(value)
    
    def __str__(self):
        return f"{self.name} for {self.dataset}"

class CensusTag(models.Model):
    """Model to store Census dataset tags"""
    
    name = models.CharField(max_length=100, primary_key=True)
    
    # Many-to-many relationship with datasets
    datasets = models.ManyToManyField(CensusDataset, related_name='tags')
    
    def __str__(self):
        return self.name

class CensusFIPSCode(models.Model):
    """Model to store FIPS codes for geographic entities"""
    
    # Unique identifier
    id = models.AutoField(primary_key=True)
    
    # FIPS details
    geo_type = models.CharField(max_length=100)  # e.g., "state", "county"
    fips_code = models.CharField(max_length=50)  # e.g., "06" for California
    name = models.CharField(max_length=255)  # e.g., "California"
    
    # For counties and other sub-entities
    parent_geo_type = models.CharField(max_length=100, blank=True, null=True)  # e.g., "state"
    parent_fips_code = models.CharField(max_length=50, blank=True, null=True)  # e.g., "06"
    
    class Meta:
        unique_together = ('geo_type', 'fips_code')
        indexes = [
            models.Index(fields=['geo_type', 'fips_code']),
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.geo_type}:{self.fips_code})"

class CensusQueryMapping(models.Model):
    """Model to store semantic mappings between natural language queries and Census variables"""
    
    # Unique identifier
    id = models.AutoField(primary_key=True)
    
    # Query pattern and mapping
    query_pattern = models.CharField(max_length=500)  # e.g., "hispanic population"
    dataset = models.ForeignKey(CensusDataset, on_delete=models.CASCADE, related_name='query_mappings')
    variable = models.ForeignKey(CensusVariable, on_delete=models.CASCADE, related_name='query_mappings')
    relevance_score = models.FloatField(default=0.0)  # 0-1 score of relevance
    
    # For tracking effectiveness
    usage_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    
    # Fields for search optimization
    query_embedding = models.BinaryField(blank=True, null=True)  # For vector search
    
    class Meta:
        indexes = [
            models.Index(fields=['query_pattern']),
            models.Index(fields=['relevance_score']),
        ]
    
    def __str__(self):
        return f"{self.query_pattern} → {self.variable.variable_name}"


class Feedback(models.Model):
    """Model to store user feedback without requiring authentication"""
    
    # Feedback types as choices for validation
    FEEDBACK_TYPES = [
        ('suggestion', 'Suggestion'),
        ('bug', 'Bug Report'),
        ('feature_request', 'Feature Request'),
        ('praise', 'Praise'),
    ]
    
    # Status options as choices
    STATUS_CHOICES = [
        ('new', 'New'),
        ('in_review', 'In Review'),
        ('planned', 'Planned'),
        ('implemented', 'Implemented'),
        ('declined', 'Declined'),
    ]
    
    # Core fields
    feedback_type = models.CharField(max_length=50, choices=FEEDBACK_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='new')
    email = models.EmailField(blank=True, null=True)
    page_url = models.URLField(max_length=512, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Engagement
    upvotes = models.IntegerField(default=0)
    
    # Using PostgreSQL-specific fields
    tags = ArrayField(models.CharField(max_length=100), blank=True, default=list)
    metadata = models.JSONField(blank=True, null=True)
    
    class Meta:
        app_label = 'factchecker'
        db_table = 'factchecker_feedback'
        indexes = [
            models.Index(fields=['feedback_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.feedback_type}: {self.title}"