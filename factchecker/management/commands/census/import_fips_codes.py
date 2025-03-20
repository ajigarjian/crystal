import csv
import requests
from io import StringIO
from django.core.management.base import BaseCommand
from factchecker.models import CensusFIPSCode


class Command(BaseCommand):
    help = 'Import FIPS codes for states and counties from Census data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing FIPS codes before importing'
        )

    def handle(self, *args, **options):
        clear_data = options.get('clear', False)
        
        self.stdout.write(self.style.SUCCESS('Starting import of FIPS codes'))
        
        # Clear existing data if requested
        if clear_data:
            CensusFIPSCode.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing FIPS codes'))
        
        # Import state FIPS codes
        self.stdout.write('1. Importing state FIPS codes...')
        self._import_state_fips()
        
        # Import county FIPS codes
        self.stdout.write('2. Importing county FIPS codes...')
        self._import_county_fips()
        
        # Print stats
        state_count = CensusFIPSCode.objects.filter(geo_type='state').count()
        county_count = CensusFIPSCode.objects.filter(geo_type='county').count()
        
        self.stdout.write(self.style.SUCCESS('\nImport Statistics:'))
        self.stdout.write(f'  States: {state_count}')
        self.stdout.write(f'  Counties: {county_count}')
        self.stdout.write(self.style.SUCCESS('FIPS codes import completed!'))
    
    def _import_state_fips(self):
        """Import state FIPS codes"""
        # State FIPS codes as a list of (code, name) tuples
        STATE_FIPS = [
            ("01", "Alabama"),
            ("02", "Alaska"),
            ("04", "Arizona"),
            ("05", "Arkansas"),
            ("06", "California"),
            ("08", "Colorado"),
            ("09", "Connecticut"),
            ("10", "Delaware"),
            ("11", "District of Columbia"),
            ("12", "Florida"),
            ("13", "Georgia"),
            ("15", "Hawaii"),
            ("16", "Idaho"),
            ("17", "Illinois"),
            ("18", "Indiana"),
            ("19", "Iowa"),
            ("20", "Kansas"),
            ("21", "Kentucky"),
            ("22", "Louisiana"),
            ("23", "Maine"),
            ("24", "Maryland"),
            ("25", "Massachusetts"),
            ("26", "Michigan"),
            ("27", "Minnesota"),
            ("28", "Mississippi"),
            ("29", "Missouri"),
            ("30", "Montana"),
            ("31", "Nebraska"),
            ("32", "Nevada"),
            ("33", "New Hampshire"),
            ("34", "New Jersey"),
            ("35", "New Mexico"),
            ("36", "New York"),
            ("37", "North Carolina"),
            ("38", "North Dakota"),
            ("39", "Ohio"),
            ("40", "Oklahoma"),
            ("41", "Oregon"),
            ("42", "Pennsylvania"),
            ("44", "Rhode Island"),
            ("45", "South Carolina"),
            ("46", "South Dakota"),
            ("47", "Tennessee"),
            ("48", "Texas"),
            ("49", "Utah"),
            ("50", "Vermont"),
            ("51", "Virginia"),
            ("53", "Washington"),
            ("54", "West Virginia"),
            ("55", "Wisconsin"),
            ("56", "Wyoming"),
            ("60", "American Samoa"),
            ("66", "Guam"),
            ("69", "Commonwealth of the Northern Mariana Islands"),
            ("72", "Puerto Rico"),
            ("78", "U.S. Virgin Islands")
        ]
        
        # Create state FIPS records
        states_to_create = []
        for fips_code, name in STATE_FIPS:
            states_to_create.append(
                CensusFIPSCode(
                    geo_type='state',
                    fips_code=fips_code,
                    name=name
                )
            )
        
        # Bulk create states
        CensusFIPSCode.objects.bulk_create(
            states_to_create,
            ignore_conflicts=True
        )
        
        self.stdout.write(self.style.SUCCESS(f'Imported {len(states_to_create)} state FIPS codes'))
    
    def _import_county_fips(self):
        """Import county FIPS codes by downloading data from Census"""
        # URL for 2020 county FIPS codes
        url = "https://www2.census.gov/programs-surveys/popest/geographies/2020/all-geocodes-v2020.xlsx"
        
        try:
            # Use a service to convert Excel to CSV
            convert_url = f"https://convertexcel.net/v1/?url={url}&format=csv"
            response = requests.get(convert_url)
            
            if response.status_code != 200:
                # Alternative: Try direct download and use pandas (need to install pandas and openpyxl)
                self.stdout.write('Using alternative county FIPS code source...')
                self._import_county_fips_alternative()
                return
            
            # Parse CSV data
            csv_data = StringIO(response.text)
            reader = csv.reader(csv_data)
            
            # Skip header rows
            next(reader)  # Skip header row
            
            # Process county rows
            counties_to_create = []
            for row in reader:
                # Check if this is a county row (summary level 050)
                if len(row) >= 4 and row[0] == '050':
                    state_code = row[1]
                    county_code = row[2]
                    county_name = row[3].replace(' County', '').strip()
                    
                    # Full county FIPS is state + county code
                    county_fips = f"{state_code}{county_code}"
                    
                    counties_to_create.append(
                        CensusFIPSCode(
                            geo_type='county',
                            fips_code=county_fips,
                            name=county_name,
                            parent_geo_type='state',
                            parent_fips_code=state_code
                        )
                    )
            
            # Bulk create counties
            CensusFIPSCode.objects.bulk_create(
                counties_to_create,
                ignore_conflicts=True
            )
            
            self.stdout.write(self.style.SUCCESS(f'Imported {len(counties_to_create)} county FIPS codes'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing county FIPS: {str(e)}'))
            # Try alternative method
            self._import_county_fips_alternative()
    
    def _import_county_fips_alternative(self):
        """Alternative method to import county FIPS using hardcoded data"""
        # Hardcode some major counties for essential coverage
        MAJOR_COUNTIES = [
            # Format: (county_fips, county_name, state_fips)
            ("06037", "Los Angeles", "06"),  # Los Angeles, CA
            ("06075", "San Francisco", "06"),  # San Francisco, CA
            ("06085", "Santa Clara", "06"),  # Santa Clara, CA
            ("36061", "New York", "36"),  # New York, NY
            ("36047", "Kings", "36"),  # Brooklyn, NY
            ("36059", "Nassau", "36"),  # Nassau, NY
            ("36081", "Queens", "36"),  # Queens, NY
            ("36103", "Suffolk", "36"),  # Suffolk, NY
            ("17031", "Cook", "17"),  # Chicago, IL
            ("48201", "Harris", "48"),  # Houston, TX
            ("48113", "Dallas", "48"),  # Dallas, TX
            ("48439", "Tarrant", "48"),  # Fort Worth, TX
            ("06073", "San Diego", "06"),  # San Diego, CA
            ("12086", "Miami-Dade", "12"),  # Miami, FL
            ("04013", "Maricopa", "04"),  # Phoenix, AZ
            ("42101", "Philadelphia", "42"),  # Philadelphia, PA
            ("25025", "Suffolk", "25"),  # Boston, MA
            ("53033", "King", "53"),  # Seattle, WA
            ("06067", "Sacramento", "06"),  # Sacramento, CA
            ("29189", "St. Louis", "29"),  # St. Louis, MO
        ]
        
        counties_to_create = []
        for county_fips, county_name, state_fips in MAJOR_COUNTIES:
            counties_to_create.append(
                CensusFIPSCode(
                    geo_type='county',
                    fips_code=county_fips,
                    name=county_name,
                    parent_geo_type='state',
                    parent_fips_code=state_fips
                )
            )
        
        # Bulk create counties
        CensusFIPSCode.objects.bulk_create(
            counties_to_create,
            ignore_conflicts=True
        )
        
        self.stdout.write(self.style.SUCCESS(f'Imported {len(counties_to_create)} county FIPS codes (alternative method)'))
        self.stdout.write(self.style.WARNING('Only imported major counties. For complete coverage, try again later.')) 