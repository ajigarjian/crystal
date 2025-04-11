from django.core.management.base import BaseCommand
from django.utils import timezone
import json
from datetime import datetime, timedelta
from factchecker.models import DataGovArchiveCheck, DatasetResource

class Command(BaseCommand):
    help = 'Updates dataset status tracking fields to identify linkrot and missing datasets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mark-missing',
            action='store_true',
            help='Mark datasets not seen in the last 30 days as missing from Data.gov',
        )
        parser.add_argument(
            '--detect-broken',
            action='store_true',
            help='Detect datasets where all resources have gone bad',
        )
        parser.add_argument(
            '--initialize-history',
            action='store_true',
            help='Initialize availability history for datasets missing it',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting dataset status tracking update...')
        
        stats = {
            'datasets_processed': 0,
            'datasets_marked_missing': 0,
            'datasets_with_bad_resources': 0,
            'history_initialized': 0,
        }
        
        # Process all DataGovArchiveCheck records
        for check in DataGovArchiveCheck.objects.all():
            updated = False
            
            # Initialize basic tracking fields if they're None
            if check.resources_checked is None:
                check.resources_checked = 0
                updated = True
                
            if check.resources_available is None:
                check.resources_available = 0
                updated = True
            
            # Set last_available_in_datagov if it's None
            if not hasattr(check, 'last_available_in_datagov') or check.last_available_in_datagov is None:
                check.last_available_in_datagov = check.last_checked_at or check.created_at or timezone.now()
                updated = True
            
            # Set is_still_in_datagov if it's None
            if not hasattr(check, 'is_still_in_datagov'):
                check.is_still_in_datagov = True
                updated = True
            
            # Calculate if dataset has or had resources
            dataset_resources = DatasetResource.objects.filter(dataset__dataset_id=check.dataset_name)
            resources_count = dataset_resources.count()
            available_resources_count = dataset_resources.filter(is_available=True).count()
            
            # Set had_resources
            if not hasattr(check, 'had_resources') or check.had_resources is None:
                check.had_resources = resources_count > 0
                updated = True
            
            # Set has_usable_resources
            if not hasattr(check, 'has_usable_resources') or check.has_usable_resources is None:
                check.has_usable_resources = available_resources_count > 0
                updated = True
            
            # Detect when resources have gone bad (previously had resources, now all unavailable)
            if options['detect_broken'] and check.had_resources and resources_count > 0 and available_resources_count == 0:
                check.resources_gone_bad = True
                self.stdout.write(self.style.WARNING(
                    f'Dataset {check.dataset_name} resources have gone bad! '
                    f'All {resources_count} resources are unavailable.'
                ))
                stats['datasets_with_bad_resources'] += 1
                updated = True
            
            # Mark datasets as missing from Data.gov if they haven't been seen recently
            if options['mark_missing'] and check.is_still_in_datagov:
                thirty_days_ago = timezone.now() - timedelta(days=30)
                if check.last_checked_at and check.last_checked_at < thirty_days_ago:
                    check.is_still_in_datagov = False
                    self.stdout.write(self.style.WARNING(
                        f'Dataset {check.dataset_name} marked as missing from Data.gov - '
                        f'not seen since {check.last_checked_at.strftime("%Y-%m-%d")}'
                    ))
                    stats['datasets_marked_missing'] += 1
                    updated = True
            
            # Set last_check_with_usable_resources
            if not hasattr(check, 'last_check_with_usable_resources') or check.last_check_with_usable_resources is None:
                if available_resources_count > 0:
                    check.last_check_with_usable_resources = check.last_checked_at or timezone.now()
                    updated = True
            
            # Initialize availability history if requested and it doesn't exist
            if options['initialize_history'] and (not hasattr(check, 'availability_history') or check.availability_history is None):
                now = timezone.now()
                history_entry = {
                    "date": now.isoformat(),
                    "resources_checked": resources_count,
                    "resources_available": available_resources_count,
                    "has_usable_resources": available_resources_count > 0,
                }
                check.availability_history = [history_entry]
                stats['history_initialized'] += 1
                updated = True
            
            # Save if any fields were updated
            if updated:
                check.save()
                stats['datasets_processed'] += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'Dataset status tracking update completed.\n'
            f'Processed: {stats["datasets_processed"]} datasets\n'
            f'Marked missing: {stats["datasets_marked_missing"]} datasets\n'
            f'Detected with bad resources: {stats["datasets_with_bad_resources"]} datasets\n'
            f'History initialized: {stats["history_initialized"]} datasets'
        ))