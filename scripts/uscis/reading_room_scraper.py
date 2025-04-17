import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
from urllib.parse import urljoin, parse_qs, urlparse

class USCISReadingRoomRequestsScraper:
    def __init__(self, output_file="uscis_reading_room_data.json"):
        self.base_url = "https://www.uscis.gov/records/electronic-reading-room"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }
        # File extensions we're interested in
        self.target_extensions = ['.csv', '.xls', '.xlsx', '.xml', '.json']
        # Output file
        self.output_file = output_file
        # Store results
        self.results = []
        
        # Load existing results if file exists
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.results = json.load(f)
                print(f"Loaded existing results from {self.output_file}")
            except json.JSONDecodeError:
                print(f"Error loading existing results from {self.output_file}. Starting fresh.")
                self.results = []
        
    def get_categories(self):
        """Get all categories from the filter dropdown"""
        response = self.session.get(self.base_url, headers=self.headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        categories = []
        select_element = soup.select_one('select[name="topic_id[]"]')
        
        if select_element:
            for option in select_element.find_all('option'):
                value = option.get('value')
                text = option.text.strip()
                
                # Skip the "Filter by category" option (empty value)
                if value and text != "Filter by category":
                    categories.append({"id": value, "name": text})
        
        return categories
    
    def find_structured_data_files(self, soup):
        """Find and extract structured data files from the page"""
        files_found = []
        
        # Look for file links in the document listings
        file_links = soup.select('.views-field-field-document a')
        
        for link in file_links:
            href = link.get('href')
            if not href:
                continue
                
            # Make sure the URL is absolute
            full_url = urljoin("https://www.uscis.gov", href)
            
            # Check if the link is to a file of interest
            if any(full_url.lower().endswith(ext) for ext in self.target_extensions):
                # Extract file title
                title_element = link.text.strip()
                # Remove the file size info which is typically in parentheses at the end
                title = re.sub(r'\s*\(PDF,.*?\)|\s*\(.*?KB\)|\s*\(.*?MB\)', '', title_element).strip()
                
                # Try to find the date
                date = None
                parent_row = link.find_parent('.views-row')
                if parent_row:
                    date_element = parent_row.select_one('.views-field-field-display-date time')
                    if date_element:
                        date = date_element.text.strip()
                
                # Determine file type from extension
                file_type = os.path.splitext(full_url)[1].lower().lstrip('.')
                
                files_found.append({
                    "title": title,
                    "url": full_url,
                    "date": date,
                    "type": file_type
                })
        
        return files_found
    
    def get_next_page_url(self, soup, current_url):
        """Extract the URL of the next page if it exists"""
        next_link = soup.select_one('.pager__item--next a')
        if next_link and next_link.get('href'):
            return urljoin("https://www.uscis.gov", next_link.get('href'))
        return None
    
    def scrape_category(self, category_id, category_name):
        """Scrape all pages for a specific category"""
        print(f"Scraping category: {category_name} (ID: {category_id})")
        
        # Check if we've already scraped this category
        for category in self.results:
            if category["category_id"] == category_id:
                print(f"  Skipping category {category_name} - already scraped")
                return category["files"]
        
        # Construct the URL with the category filter
        url = f"{self.base_url}?topic_id[]={category_id}"
        category_results = []
        page_num = 0
        
        while url:
            page_num += 1
            print(f"  - Processing page {page_num}: {url}")
            
            response = self.session.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find structured data files
            files = self.find_structured_data_files(soup)
            if files:
                category_results.extend(files)
                
                # Incrementally save results after each page
                self.results.append({
                    "category_id": category_id,
                    "category_name": category_name,
                    "files": category_results,
                    "last_page_processed": page_num,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                self.save_results()
                
                # Remove the entry we just added since we'll add a complete one at the end
                self.results.pop()
            
            # Check if there's a next page
            url = self.get_next_page_url(soup, url)
            
            # Be nice to the server with a small delay
            if url:
                time.sleep(1)
        
        print(f"  Found {len(category_results)} structured data files for category: {category_name}")
        return category_results
    
    def scrape_all_categories(self, start_category_id=None):
        """Scrape all categories and compile the results, optionally starting from a specific category."""
        categories = self.get_categories()
        print(f"Found {len(categories)} categories to scrape")
        
        # Get list of category IDs already processed
        processed_category_ids = [category["category_id"] for category in self.results]
        
        # Flag to indicate if we should start processing
        start_processing = start_category_id is None
        
        for i, category in enumerate(categories):
            category_id = category["id"]
            category_name = category["name"]
            
            # Check if this is the starting category
            if not start_processing and category_id == start_category_id:
                print(f"Starting processing from category: {category_name} (ID: {category_id})")
                start_processing = True
                
            # Skip if we haven't reached the starting category yet
            if not start_processing:
                print(f"[{i+1}/{len(categories)}] Skipping {category_name} - before start category")
                continue

            # Skip if already processed
            if category_id in processed_category_ids:
                print(f"[{i+1}/{len(categories)}] Skipping {category_name} - already processed")
                continue
                
            print(f"[{i+1}/{len(categories)}] ", end="")
            category_files = self.scrape_category(category_id, category_name)
            
            if category_files:
                self.results.append({
                    "category_id": category_id,
                    "category_name": category_name,
                    "files": category_files,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                # Save after each category is processed
                self.save_results()
        
        return self.results
    
    def save_results(self):
        """Save the results to the output file"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"Results saved to {self.output_file}")

if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Scrape structured data files from USCIS Electronic Reading Room')
    parser.add_argument('--output', '-o', default='uscis_reading_room_data.json',
                      help='Output file path (default: uscis_reading_room_data.json)')
    parser.add_argument('--category', '-c', 
                      help='Scrape only a specific category ID')
    parser.add_argument('--delay', '-d', type=float, default=1.0,
                      help='Delay between requests in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    # Define the starting category ID
    START_CATEGORY_ID = "33679" # Public Charge
    
    # Initialize the scraper
    scraper = USCISReadingRoomRequestsScraper(output_file=args.output)
    
    try:
        # If a specific category ID is provided
        if args.category:
            categories = scraper.get_categories()
            for category in categories:
                if category["id"] == args.category:
                    print(f"Scraping only category: {category['name']} (ID: {args.category})")
                    files = scraper.scrape_category(args.category, category["name"])
                    if files:
                        # Check if category already exists in results
                        category_exists = False
                        for i, result_category in enumerate(scraper.results):
                            if result_category["category_id"] == args.category:
                                # Update existing category
                                scraper.results[i] = {
                                    "category_id": args.category,
                                    "category_name": category["name"],
                                    "files": files,
                                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                category_exists = True
                                break
                        
                        if not category_exists:
                            # Add new category
                            scraper.results.append({
                                "category_id": args.category,
                                "category_name": category["name"],
                                "files": files,
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            })
                        
                        scraper.save_results()
                    break
            else:
                print(f"Category ID {args.category} not found!")
        else:
            # Scrape all categories starting from the specified one
            results = scraper.scrape_all_categories(start_category_id=START_CATEGORY_ID)
        
        # Print a summary
        total_files = sum(len(category["files"]) for category in scraper.results)
        print(f"\nScraping completed!")
        print(f"Found {total_files} structured data files across {len(scraper.results)} categories")
        print(f"Results saved to {args.output}")
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user!")
        print("Partial results have been saved.")