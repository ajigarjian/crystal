from django.core.management.base import BaseCommand
import json
from datetime import datetime
from factchecker.models import DataGovArchiveCheck, ResourceAvailabilityCheck, DatasetResource

class Command(BaseCommand):
    help = 'Extracts JSON data into structured fields for linkrot tracking'

    def handle(self, *args, **options):
        self.stdout.write('Starting linkrot tracking data extraction...')
        
        # Process DataGovArchiveCheck records
        for check in DataGovArchiveCheck.objects.all():
            if check.error:
                try:
                    error_data = json.loads(check.error)
                    if isinstance(error_data, dict):
                        check.resources_checked = error_data.get('resources_checked', 0)
                        check.resources_available = error_data.get('resources_available', 0)
                        check.save()
                except json.JSONDecodeError:
                    self.stdout.write(self.style.WARNING(f'Could not parse error JSON for {check.dataset_name}'))
        
        # Process ResourceAvailabilityCheck records
        for check in ResourceAvailabilityCheck.objects.all():
            if check.error_message:
                try:
                    error_data = json.loads(check.error_message)
                    if isinstance(error_data, dict):
                        check.http_status = error_data.get('http_status')
                        check.response_time_ms = error_data.get('response_time_ms')
                        check.save()
                except json.JSONDecodeError:
                    self.stdout.write(self.style.WARNING(f'Could not parse error JSON for resource check {check.id}'))
        
        # Update DatasetResource records
        for resource in DatasetResource.objects.all():
            if resource.availability_history:
                try:
                    history = json.loads(resource.availability_history)
                    if isinstance(history, list) and len(history) > 0:
                        latest_check = history[-1]
                        resource.last_availability_check = datetime.fromisoformat(latest_check.get('check_datetime'))
                        resource.is_available = latest_check.get('is_available', True)
                        resource.save()
                except (json.JSONDecodeError, ValueError):
                    self.stdout.write(self.style.WARNING(f'Could not parse availability history for resource {resource.id}'))
        
        self.stdout.write(self.style.SUCCESS('Linkrot tracking data extraction completed.')) 