from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.conf import settings
from django.apps import apps
from django.db.models import Q

class Command(BaseCommand):
    help = 'Migrate data from SQLite to PostgreSQL'

    def handle(self, *args, **options):
        self.stdout.write("Clearing all data from PostgreSQL database...")
        
        # Get all models in reverse order (to handle foreign key dependencies)
        all_models = list(apps.get_models())
        all_models.reverse()
        
        # First, clear all data from PostgreSQL
        with transaction.atomic(using='postgres'):
            for model in all_models:
                self.stdout.write(f"  Clearing {model.__name__}")
                try:
                    # Delete all records
                    model.objects.using('postgres').all().delete()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error clearing {model.__name__}: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS("PostgreSQL database cleared successfully"))
        
        # Now migrate data from SQLite to PostgreSQL
        # Reset the model order for insertion
        all_models.reverse()
        
        for model in all_models:
            self.stdout.write(f"Migrating {model.__name__}")
            
            # Get all data from SQLite
            try:
                objects = model.objects.using('default').all()
                count = objects.count()
                
                if count > 0:
                    self.stdout.write(f"  Copying {count} records")
                    
                    # Save to PostgreSQL
                    with transaction.atomic(using='postgres'):
                        for obj in objects:
                            # Create a new instance with the same data
                            new_obj = model()
                            for field in obj._meta.fields:
                                if field.primary_key:
                                    # Keep the same primary key
                                    setattr(new_obj, field.name, obj.pk)
                                else:
                                    setattr(new_obj, field.name, getattr(obj, field.name))
                            
                            # Save to PostgreSQL without validation
                            try:
                                new_obj.save(using='postgres', force_insert=True)
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"    Error saving object {obj.pk}: {str(e)}"))
                    
                    self.stdout.write(self.style.SUCCESS(f"  Successfully migrated {model.__name__}"))
                else:
                    self.stdout.write(f"  No records to migrate for {model.__name__}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error migrating {model.__name__}: {str(e)}"))