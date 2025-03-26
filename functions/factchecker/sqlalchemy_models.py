from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float, UniqueConstraint, Index, Table
from sqlalchemy.types import LargeBinary, TypeDecorator  # Add TypeDecorator
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import json
from datetime import datetime
import base64

# Custom type for handling binary embeddings
class BinaryEmbedding(TypeDecorator):
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        """Process the value before it's sent to the database"""
        if value is None:
            return None
            
        # If it's already a PostgreSQL bytea literal string (starts with \x)
        if isinstance(value, str) and value.startswith('\\x'):
            return value
            
        # If it's bytes, convert to PostgreSQL bytea format
        if isinstance(value, bytes):
            return '\\x' + value.hex()
            
        # If it's a numpy array, convert to bytes then to hex
        if hasattr(value, 'tobytes'):
            return '\\x' + value.tobytes().hex()
            
        # If it's a list, convert to numpy array, then to bytes, then to hex
        if isinstance(value, list):
            import numpy as np
            arr = np.array(value, dtype=np.float32)
            return '\\x' + arr.tobytes().hex()
            
        # For other types, try JSON
        return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        """Process the value when it's retrieved from the database."""
        if value is None:
            return None
        
        # If it's a PostgreSQL bytea string (starts with \x):
        if isinstance(value, str) and value.startswith('\\x'):
            try:
                binary_data = bytes.fromhex(value[2:])
                # Attempt float32 only if divisible by 4:
                if len(binary_data) % 4 == 0:
                    import numpy as np
                    try:
                        # Attempt to interpret as float32 array
                        return np.frombuffer(binary_data, dtype=np.float32)
                    except Exception:
                        # If float32 parse fails, just return raw bytes
                        return binary_data
                else:
                    # If the size isn't a multiple of 4, just return raw bytes
                    return binary_data
            except Exception as e:
                print(f"Error processing bytea embedding: {e}")
                return value
        
        # If it's a regular string (JSON or otherwise), try loading JSON
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return value
        
        # Otherwise, return as is
        return value

Base = declarative_base()

class DatasetCatalog(Base):
    """Model to store dataset metadata from Data.gov with vector search support"""
    __tablename__ = 'factchecker_datasetcatalog'
    
    # Primary fields from the JSON data
    dataset_id = Column(String(255), primary_key=True)
    title = Column(String(500))
    notes = Column(Text, nullable=True)
    organization_name = Column(String(255), nullable=True)
    organization_title = Column(String(500), nullable=True)
    organization_description = Column(Text, nullable=True)
    
    # New field for tags (stored as JSON string)
    tags_json = Column(Text, nullable=True)
    
    # Fields for search optimization
    search_text = Column(Text, nullable=True)  # Combined text for basic search
    
    # Field for vector embeddings (stored as binary)
    embedding = Column(BinaryEmbedding, nullable=True)
    
    # Metadata fields
    indexed = Column(Boolean, default=False)  # Whether embedding has been generated
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Additional fields for DatasetCatalog
    license_id = Column(String(100), nullable=True)
    license_title = Column(String(255), nullable=True)
    license_url = Column(String(1000), nullable=True)
    maintainer = Column(String(255), nullable=True)
    maintainer_email = Column(String(255), nullable=True)
    metadata_created = Column(DateTime, nullable=True)
    metadata_modified = Column(DateTime, nullable=True)
    extras_json = Column(Text, nullable=True)  # Store extras as JSON
    groups_json = Column(Text, nullable=True)  # Store groups as JSON
    
    # New field for image URL
    image_url = Column(String(1000), nullable=True)
    
    # Define the relationship with resources
    resources = relationship("DatasetResource", back_populates="dataset")
    
    # Define indexes
    __table_args__ = (
        Index('ix_dataset_catalog_title', 'title'),
        Index('ix_dataset_catalog_organization_name', 'organization_name'),
    )
    
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

class DatasetResource(Base):
    """Model to store dataset resources"""
    __tablename__ = 'factchecker_datasetresource'
    
    id = Column(Integer, primary_key=True)
    dataset_id = Column(String(255), ForeignKey('factchecker_datasetcatalog.dataset_id'))
    name = Column(String(255))
    url = Column(String(1000), nullable=True)
    description = Column(Text, nullable=True)
    format = Column(String(50), nullable=True)
    
    # Define the relationship with the dataset
    dataset = relationship("DatasetCatalog", foreign_keys=[dataset_id])
    
    def __str__(self):
        return f"{self.name} ({self.format})"

class CensusDataset(Base):
    """Model to store Census API dataset metadata"""
    __tablename__ = 'factchecker_censusdataset'
    
    # Unique identifier - combination of vintage and dataset path
    id = Column(Integer, primary_key=True, autoincrement=True)
    vintage = Column(Integer)  # Year (e.g., 2020)
    dataset_path = Column(String(255))  # e.g., "acs/acs5"
    
    # Basic metadata
    title = Column(String(500))
    description = Column(Text, nullable=True)
    
    # Type of dataset
    is_aggregate = Column(Boolean, default=False)
    is_microdata = Column(Boolean, default=False)
    
    # Temporal coverage
    reference_period = Column(String(50), nullable=True)  # e.g., "2016-2020"
    modified_date = Column(String(50), nullable=True)  # Changed from DateTime to String
    
    # API endpoint
    api_endpoint = Column(String(500))
    
    # Fields for search optimization
    embedding = Column(BinaryEmbedding, nullable=True)  # For vector search - stored as TEXT in PostgreSQL bytea format
    
    # Metadata fields
    created_at = Column(String(50), default=lambda: datetime.now().isoformat())  # Changed from DateTime to String
    updated_at = Column(String(50), default=lambda: datetime.now().isoformat(), 
                        onupdate=lambda: datetime.now().isoformat())  # Changed from DateTime to String
    
    # Define unique constraint and indexes
    __table_args__ = (
        UniqueConstraint('vintage', 'dataset_path', name='uq_census_dataset_vintage_path'),
        Index('ix_census_dataset_vintage', 'vintage'),
        Index('ix_census_dataset_dataset_path', 'dataset_path'),
    )
    
    # Add the many-to-many relationship with CensusTag
    tags = relationship("CensusTag", secondary="factchecker_censustag_datasets", 
                        backref="datasets")
    
    # Add relationships to related models
    geographies = relationship("CensusGeography", back_populates="dataset")
    variables = relationship("CensusVariable", back_populates="dataset")
    groups = relationship("CensusGroup", back_populates="dataset")
    
    def __str__(self):
        return f"{self.vintage} {self.title}"

class CensusVariable(Base):
    """Model to store Census variables within datasets"""
    __tablename__ = 'factchecker_censusvariable'
    
    # Unique identifier
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to the dataset
    dataset_id = Column(Integer, ForeignKey('factchecker_censusdataset.id'))
    
    # Variable details
    variable_name = Column(String(100))  # e.g., "B01001_001E"
    label = Column(Text)  # e.g., "Estimate!!Total:"
    concept = Column(String(500), nullable=True)  # e.g., "SEX BY AGE"
    group_name = Column(String(100), nullable=True)  # e.g., "B01001"
    predicate_type = Column(String(50), nullable=True)  # e.g., "int"
    
    # Fields for search optimization
    embedding = Column(BinaryEmbedding, nullable=True)  # For semantic search
    
    # Add the relationship with the dataset
    dataset = relationship("CensusDataset", back_populates="variables")
    
    # Define unique constraint and indexes
    __table_args__ = (
        UniqueConstraint('dataset_id', 'variable_name', name='uq_census_variable_dataset_name'),
        Index('ix_census_variable_variable_name', 'variable_name'),
        Index('ix_census_variable_group_name', 'group_name'),
        Index('ix_census_variable_concept', 'concept'),
    )
    
    def __str__(self):
        return f"{self.variable_name} - {self.label}"

class CensusGroup(Base):
    """Model to store Census groups (tables) within datasets"""
    __tablename__ = 'factchecker_censusgroup'
    
    # Unique identifier
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to the dataset
    dataset_id = Column(Integer, ForeignKey('factchecker_censusdataset.id'))
    
    # Group details
    name = Column(String(100))  # e.g., "B01001"
    description = Column(Text, nullable=True)
    variables_url = Column(String(500), nullable=True)  # Link to variables data
    
    # Fields for search optimization
    embedding = Column(BinaryEmbedding, nullable=True)  # For semantic search
    
    # Add the relationship with the dataset
    dataset = relationship("CensusDataset", back_populates="groups")
    
    # Define unique constraint and indexes
    __table_args__ = (
        UniqueConstraint('dataset_id', 'name', name='uq_census_group_dataset_name'),
        Index('ix_census_group_name', 'name'),
    )
    
    def __str__(self):
        return f"{self.name} - {self.description}"

class CensusGeography(Base):
    """Model to store Census geographic levels available for datasets"""
    __tablename__ = 'factchecker_censusgeography'
    
    # Unique identifier
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to the dataset
    dataset_id = Column(Integer, ForeignKey('factchecker_censusdataset.id'))
    
    # Geography details
    name = Column(String(100))  # e.g., "state", "county"
    geo_level_display = Column(String(10), nullable=True)  # e.g., "040"
    reference_date = Column(DateTime, nullable=True)
    
    # Required and wildcard geographies (stored as JSON)
    requires_json = Column(Text, nullable=True)  # e.g., ["state"]
    wildcard_json = Column(Text, nullable=True)  # e.g., ["state"]
    
    # Add the relationship with the dataset
    dataset = relationship("CensusDataset", back_populates="geographies")
    
    # Define unique constraint and indexes
    __table_args__ = (
        UniqueConstraint('dataset_id', 'name', name='uq_census_geography_dataset_name'),
        Index('ix_census_geography_name', 'name'),
    )
    
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

class CensusTag(Base):
    """Model to store Census dataset tags for categorization"""
    __tablename__ = 'factchecker_censustag'
    
    # Use name as primary key for easier lookups
    name = Column(String(100), primary_key=True)
    # Remove the description field if it doesn't exist in your database
    # description = Column(Text, nullable=True)
    
    def __str__(self):
        return self.name

class CensusFIPSCode(Base):
    """Model to store FIPS codes for geographic entities"""
    __tablename__ = 'factchecker_censusfipscode'
    
    # Unique identifier
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # FIPS code details - update to match database columns
    fips_code = Column(String(10))  # Changed from 'code' to 'fips_code'
    name = Column(String(255))
    geo_type = Column(String(50))  # e.g., "state", "county", "place"
    
    # Hierarchical relationships - update to match database columns
    parent_geo_type = Column(String(50), nullable=True)  # Added to match DB
    parent_fips_code = Column(String(10), nullable=True)  # Added to match DB
    
    # Define indexes
    __table_args__ = (
        Index('ix_census_fips_fips_code', 'fips_code'),  # Updated index name
        Index('ix_census_fips_name', 'name'),
        Index('ix_census_fips_geo_type', 'geo_type'),
    )
    
    def __str__(self):
        return f"{self.name} ({self.fips_code})"  # Updated to use fips_code

# Add the many-to-many association table
class CensusTagDataset(Base):
    """Association table for Census tags and datasets"""
    __tablename__ = 'factchecker_censustag_datasets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    censustag_id = Column(String(100), ForeignKey('factchecker_censustag.name'))
    censusdataset_id = Column(Integer, ForeignKey('factchecker_censusdataset.id'))
    
    def __str__(self):
        return f"{self.censustag_id} - {self.censusdataset_id}"

# Commented out class remains commented out
# class CensusQueryMapping(Base):
#     """Model to store semantic mappings between natural language queries and Census variables"""
#     __tablename__ = 'factchecker_'
#     
#     # Unique identifier
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     
#     # Query pattern and mapping
#     query_pattern = Column(String(500))  # e.g., "hispanic population"
#     dataset_id = Column(Integer, ForeignKey('census_dataset.id'))
#     dataset = relationship("CensusDataset", back_populates="query_mappings")
#     variable_id = Column(Integer, ForeignKey('census_variable.id'))
#     variable = relationship("CensusVariable", back_populates="query_mappings")
#     relevance_score = Column(Float, default=0.0)  # 0-1 score of relevance
#     
#     # For tracking effectiveness
#     usage_count = Column(Integer, default=0)
#     success_count = Column(Integer, default=0)
#     
#     # Fields for search optimization
#     query_embedding = Column(BinaryEmbedding, nullable=True)  # For vector search
#     
#     # Define indexes
#     __table_args__ = (
#         Index('ix_census_query_mapping_query_pattern', 'query_pattern'),
#         Index('ix_census_query_mapping_relevance_score', 'relevance_score'),
#     )
#     
#     def __str__(self):
#         return f"{self.query_pattern} → {self.variable.variable_name}"