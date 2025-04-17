import pandas as pd
import json

# Define the input and output file paths
input_json_path = 'uscis_reading_room_data.json'
output_json_path = 'deduplicated_uscis_data.json'

# Read the JSON data
try:
    with open(input_json_path, 'r') as f:
        categories_data = json.load(f)
except FileNotFoundError:
    print(f"Error: Input file not found at {input_json_path}")
    exit(1)
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from {input_json_path}")
    exit(1)

# Flatten the data: Extract all file entries from each category
all_files = []
for category in categories_data:
    if 'files' in category and isinstance(category['files'], list):
        # Optionally add category info to each file record if needed
        # for file_info in category['files']:
        #     file_info['category_id'] = category.get('category_id')
        #     file_info['category_name'] = category.get('category_name')
        #     all_files.append(file_info)
        all_files.extend(category['files'])

# Convert the flattened list of file dictionaries to a pandas DataFrame
df = pd.DataFrame(all_files)

# Check if the DataFrame is empty or if the 'url' column exists
if df.empty:
    print("No file data found in the JSON structure.")
    exit(1)
if 'url' not in df.columns:
    print(f"Error: 'url' column not found in the extracted file data.")
    # Inspect the first few entries of all_files if needed
    # print("First few extracted file entries:", all_files[:5])
    exit(1)

# Get the initial number of records (individual files)
initial_count = len(df)
print(f"Initial number of file records: {initial_count}")

# Deduplicate based on the 'url' column, keeping the first occurrence
df_deduplicated = df.drop_duplicates(subset=['url'], keep='first')

# Get the number of records after deduplication
final_count = len(df_deduplicated)
print(f"Number of unique file records after deduplication: {final_count}")
print(f"Number of duplicate file records removed: {initial_count - final_count}")

# Save the deduplicated DataFrame back to a JSON file
# Convert DataFrame back to list of dictionaries for JSON output
deduplicated_data = df_deduplicated.to_dict(orient='records')

try:
    with open(output_json_path, 'w') as f:
        json.dump(deduplicated_data, f, indent=4)
    print(f"Deduplicated data saved to {output_json_path}")
except IOError:
    print(f"Error: Could not write output file to {output_json_path}")
    exit(1) 