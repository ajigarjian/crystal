# Crystal Project

A Django application that uses Data.gov datasets and OpenAI to fact-check queries.

## Features

- Search and download datasets from Data.gov
- Vector search for relevant datasets using OpenAI embeddings
- Data analysis and extraction from CSV files
- Fact-checking based on government data

## Setup

### Prerequisites

- Python 3.10+
- Django 5.1+
- Data.gov API key
- OpenAI API key

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/ajigarjian/crystal.git
   cd crystal
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root:
   ```
   cp .env.example .env
   ```
   Then edit the `.env` file to add your API keys:
   - Get a Data.gov API key from [https://api.data.gov/signup/](https://api.data.gov/signup/)
   - Get an OpenAI API key from [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

5. Database setup:
   - Run migrations: `python manage.py migrate`
   - If you want to update the pre-populated database:
     - Run `python build_dataset_catalog.py` to download the catalog
     - Import it using `python manage.py import_catalog path/to/catalog.json`
     - Generate embeddings with `python manage.py generate_embeddings`

## Note: Pre-populated Database

This repository includes a pre-populated SQLite database (`db.sqlite3`) containing:

- Approximately 300,000 records of metadata from Data.gov datasets
- Pre-generated OpenAI embeddings for vector search of each dataset's metadata

Having this database included means you can immediately start using the factchecker command without needing to:
1. Download the Data.gov catalog
2. Import it into the database
3. Generate embeddings (which would require significant OpenAI API usage)

If you want to update the database with fresh data:
1. Run `python build_dataset_catalog.py` to download the latest dataset catalog as `data_gov_catalog.json` (takes approximately 30-60 minutes)
2. Run `python manage.py import_catalog data_gov_catalog.json` to import the dataset metadata into the sqlite database (takes approximately 1 minute)
3. Run `python manage.py generate_embeddings` to create new embeddings (takes several hours; note: this will use your OpenAI API credits and will cost around $1-$2)

## Large Files

This project uses large data files that exceed GitHub's file size limits:

- `db.sqlite3` (2.8GB): Pre-populated database with 300,000 dataset records and embeddings
- `data_gov_catalog.json` (366MB): Raw dataset catalog from Data.gov

These files are available for download at: [link to cloud storage]

After cloning the repository, download these files and place them in the project root directory.

### Usage

Run the factchecker command to find data that is relevant to your query:

```bash
python manage.py factchecker "your query here"
```

For example:
```bash
python manage.py factchecker "college graduation rates in the US"
```

Specifying the Number of Datasets

Limit the number of most relevant datasets to initially download:

```bash
python manage.py factchecker "high school dropout rates" --top 3
```

This will download only the 3 most relevant datasets (default is 5).

Setting the Output Directory

Specify where downloaded datasets should be saved:

```bash
python manage.py factchecker "unemployment statistics" --output "my_data_folder"
```
This saves downloaded files to "my_data_folder" instead of the default "downloads" directory.

Showing Data Preview

Display a preview of the data:

```bash
python manage.py factchecker "covid vaccination rates" --preview
```

This displays a preview of the data in the console.

Setting Relevance Threshold
Adjust the minimum relevance score for datasets:

```bash
python manage.py factchecker "income inequality" --relevance-threshold 0.8
```

This will only use datasets with a relevance score of 0.8 or higher (default is 0.7). This is for when you have downloaded datasets and want to actually filter based on the relevance of their content.

Combined Example
You can combine multiple options:

```bash
python3 manage.py factchecker "global warming projections" --top 10 --output data_files --preview --relevance-threshold 0.5
```

This will:
- Search for datasets related to global warming projections
- Download up to the top 10 most relevant datasets out of 300,000
- Filter on those 10 datasets to only keep those with a relevance score ≥ 0.5 based on the dataset's content
- Save downloaded files to the "data_files" directory
- Show a preview of the data

## Project Structure

- `crystalproject/` - Main Django project settings
- `factchecker/` - Main application code
  - `models.py` - Database models including DatasetCatalog
  - `download_gov_data.py` - Functions for searching and downloading datasets
  - `data_analysis.py` - Functions for analyzing downloaded data
  - `management/commands/` - Custom Django management commands
    - `factchecker.py` - **Main entry point** that orchestrates the fact-checking process by calling functions from `download_gov_data.py` and `data_analysis.py`
    - `generate_embeddings.py` - Command for generating vector embeddings
    - `import_catalog.py` - Command for importing dataset catalog from JSON
- `build_dataset_catalog.py` - Script to download the Data.gov catalog
- `manage.py` - Django management script

## Development Workflow

1. Create a new branch for your feature: `git checkout -b feature-name`
2. Make your changes
3. Run tests (if available)
4. Commit your changes: `git commit -m "Description of changes"`
5. Push to your branch: `git push origin feature-name`
6. Create a pull request on GitHub