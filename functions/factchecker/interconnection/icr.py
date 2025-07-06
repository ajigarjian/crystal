import os
import json
import logging
import tempfile
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import requests
import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool
from google.cloud import storage
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import functions_framework

# ───────────── logging ─────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ───────────── constants ─────────────
PACIFIC       = ZoneInfo("America/Los_Angeles")
UTC           = ZoneInfo("UTC")
SOURCE_ID_ICR = 7
TARGET_TABLE  = "fact_icr"

# Column mapping from Excel to database
EXCEL_TO_DB_COLUMN_MAPPING = {
    "Request Number": "request_number",
    "Request Date": "request_date",
    "Project Name": "project_name",
    "Requestor": "requestor",
    "Comments": "comments",
    "Point of Interconnection": "point_of_interconnection",
    "Point Of Interconnection": "point_of_interconnection",  # Handle both cases
    "Status": "status",
    "State": "state",
    "County": "county",
    "Connection Type": "connection_type",
    "Requested In Service Date": "requested_in_service_date",
    "Requested In-Service Date": "requested_in_service_date",  # Handle actual name
    "Agreed To": "agreed_to",
    "Agreed To: (Blank=TBD)": "agreed_to",  # Handle actual name
    "Max Summer MW": "max_summer_mw",
    "Max Winter MW": "max_winter_mw",
    "Interconnection Type": "interconnection_type",
    "Generator Type 1": "generator_type_1",
    "Generator Type\n1": "generator_type_1",  # Handle newline
    "Fuel Source 1": "fuel_source_1",
    "Fuel Source\n1": "fuel_source_1",  # Handle newline
    "MW1": "mw1",
    "Generator Type 2": "generator_type_2",
    "Generator Type\n2": "generator_type_2",  # Handle newline
    "Fuel Source 2": "fuel_source_2",
    "Fuel Source\n2": "fuel_source_2",  # Handle newline
    "MW2": "mw2",
    "Generator Type 3": "generator_type_3",
    "Generator Type\n3": "generator_type_3",  # Handle newline
    "Fuel Source 3": "fuel_source_3",
    "Fuel Source\n3": "fuel_source_3",  # Handle newline
    "MW3": "mw3",
    "MW Total": "mw_total",
    "Cluster": "cluster",
    "Related Transmission Request": "related_transmission_request",
    "Reason Not Completed": "reason_not_completed",
    "Feasibility Study": "feasibility_study",
    "Phase 1 Cluster Study": "phase1_cluster_study",
    "System Impact Study": "system_impact_study",
    "Phase 2 Cluster Study": "phase2_cluster_study",
    "Facilities Study": "facilities_study",
    "Surplus Interconnection Service Request": "surplus_interconnection_service_request",
    "Repower": "repower"
}

# Pub/Sub & GCS clients (initialized lazily)
_storage_client = storage.Client()
#


# ───────────── helpers ─────────────
def download_icr_excel(url: str) -> pd.DataFrame:
    """Download the Excel and return a DataFrame of the first sheet with header row 5."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    # read into pandas; header is on the 5th row (zero-based index 4)
    df = pd.read_excel(BytesIO(resp.content), header=4)
    
    # Map Excel column names to database column names
    df = map_excel_columns_to_db(df)
    
    return df


def convert_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert DataFrame column types to match database schema."""
    df = df.copy()
    
    # Define column types based on database schema
    date_columns = [
        'request_date', 'requested_in_service_date', 'agreed_to', 
        'feasibility_study', 'phase1_cluster_study', 'system_impact_study',
        'phase2_cluster_study', 'facilities_study'
    ]
    
    numeric_columns = [
        'max_summer_mw', 'max_winter_mw', 'mw1', 'mw2', 'mw3', 'mw_total'
    ]
    
    boolean_columns = [
        'surplus_interconnection_service_request', 'repower'
    ]
    
    # Convert date columns
    for col in date_columns:
        if col in df.columns:
            # Convert to datetime, handling various formats and NaN values
            df[col] = pd.to_datetime(df[col], errors='coerce')
            # Replace NaT values with None for PostgreSQL compatibility
            df[col] = df[col].where(pd.notna(df[col]), None)
    
    # Convert numeric columns
    for col in numeric_columns:
        if col in df.columns:
            # Convert to numeric, handling NaN values
            df[col] = pd.to_numeric(df[col], errors='coerce')
            # Replace NaN values with None for PostgreSQL compatibility
            df[col] = df[col].where(pd.notna(df[col]), None)
    
    # Convert boolean columns
    for col in boolean_columns:
        if col in df.columns:
            # Convert to boolean, handling various representations
            # First convert to string to handle NaN values
            bool_series = df[col].astype(str).str.lower()
            # Handle NaN/None values
            bool_series = bool_series.replace('nan', 'false')
            # Convert to boolean
            df[col] = bool_series.isin(['true', 'yes', '1', 'y'])
            df[col] = df[col].astype(bool)
    
    # Convert text columns to string and handle NaN
    text_columns = [
        'project_name', 'requestor', 'comments', 'point_of_interconnection',
        'status', 'state', 'county', 'connection_type', 'interconnection_type',
        'generator_type_1', 'fuel_source_1', 'generator_type_2', 'fuel_source_2',
        'generator_type_3', 'fuel_source_3', 'cluster', 'related_transmission_request',
        'reason_not_completed'
    ]
    
    for col in text_columns:
        if col in df.columns:
            # Convert to string and replace NaN with None
            df[col] = df[col].astype(str).replace('nan', None)
            # Also handle empty strings and convert them to None
            df[col] = df[col].replace('', None)
    
    logger.info(f"Converted DataFrame types. Date columns: {[col for col in date_columns if col in df.columns]}")
    logger.info(f"Numeric columns: {[col for col in numeric_columns if col in df.columns]}")
    logger.info(f"Boolean columns: {[col for col in boolean_columns if col in df.columns]}")
    
    return df


def map_excel_columns_to_db(df: pd.DataFrame) -> pd.DataFrame:
    """Map Excel column names to database column names."""
    # Log the actual columns in the DataFrame for debugging
    logger.info(f"Actual DataFrame columns: {list(df.columns)}")
    
    # Create a mapping for only the columns that exist in the DataFrame
    column_mapping = {}
    unmapped_columns = []
    
    for excel_col, db_col in EXCEL_TO_DB_COLUMN_MAPPING.items():
        if excel_col in df.columns:
            column_mapping[excel_col] = db_col
    
    # Check for unmapped columns and try case-insensitive matching
    for col in df.columns:
        if col not in column_mapping:
            # Try case-insensitive matching
            matched = False
            for excel_col, db_col in EXCEL_TO_DB_COLUMN_MAPPING.items():
                if excel_col.lower() == col.lower():
                    column_mapping[col] = db_col
                    matched = True
                    break
            
            if not matched:
                unmapped_columns.append(col)
    
    # Log the mapping for debugging
    logger.info(f"Mapping columns: {column_mapping}")
    if unmapped_columns:
        logger.warning(f"Unmapped columns found: {unmapped_columns}")
    
    # Rename columns
    df = df.rename(columns=column_mapping)
    
    # Drop any unmapped columns to avoid SQL errors
    if unmapped_columns:
        logger.info(f"Dropping unmapped columns: {unmapped_columns}")
        df = df.drop(columns=unmapped_columns)
    
    logger.info(f"Final DataFrame columns after mapping: {list(df.columns)}")
    
    # Convert data types to match database schema
    df = convert_dataframe_types(df)
    
    return df


def fetch_existing_icr(conn) -> pd.DataFrame:
    """Load the existing ICR queue table into a DataFrame keyed by request_number."""
    sql = f"SELECT * FROM {TARGET_TABLE}"
    return pd.read_sql(sql, conn, index_col="request_number")


def compute_diffs(new_df: pd.DataFrame, old_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare new vs. old rows:
      • Rows present only in new_df → inserts
      • Rows present only in old_df → deletes
      • Rows in both with any changed value → updates
    Returns a diff DataFrame with columns:
      change_type (INSERT/DELETE/UPDATE), request_number, column, old, new
    """
    diffs = []
    # identify inserts and updates
    for req, new_row in new_df.iterrows():
        if req not in old_df.index:
            diffs.append({
                "change_type": "INSERT",
                "request_number": req,
                "column": None,
                "old": None,
                "new": None,
            })
        else:
            old_row = old_df.loc[req]
            for col in new_df.columns:
                if not pd.isna(old_row[col]) or not pd.isna(new_row[col]):
                    if old_row[col] != new_row[col]:
                        diffs.append({
                            "change_type": "UPDATE",
                            "request_number": req,
                            "column": col,
                            "old": old_row[col],
                            "new": new_row[col],
                        })
    # deletes
    for req in old_df.index.difference(new_df.index):
        diffs.append({
            "change_type": "DELETE",
            "request_number": req,
            "column": None,
            "old": None,
            "new": None,
        })
    return pd.DataFrame(diffs)


def upload_diff_to_gcs(df: pd.DataFrame, bucket_name: str) -> str:
    """Save diff DataFrame to CSV in GCS bucket; return the GCS URI."""
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename  = f"icr_diff_{timestamp}.csv"
    # write to a temp file
    with tempfile.NamedTemporaryFile("w+", suffix=".csv") as tmp:
        df.to_csv(tmp.name, index=False)
        bucket = _storage_client.bucket(bucket_name)
        blob   = bucket.blob(filename)
        blob.upload_from_filename(tmp.name)
    uri = f"gs://{bucket_name}/{filename}"
    logger.info("Uploaded diff file to %s", uri)
    return uri


# def publish_notification(topic: str, message: dict):
#     """Publish a JSON-encoded message to the given Pub/Sub topic."""
#     data = json.dumps(message).encode("utf-8")
#     topic_path = _publisher.topic_path(os.environ.get("GCP_PROJECT"), topic)
#     _publisher.publish(topic_path, data=data)
#     logger.info("Published Pub/Sub message to %s", topic_path)


def send_email(subject: str, html_content: str):
    """Send an email via SendGrid to NOTIFY_EMAIL addresses."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    recipients = os.environ.get("NOTIFY_EMAIL")
    if not api_key or not recipients:
        logger.info("SendGrid or recipients not configured; skipping email")
        return
    message = Mail(
        from_email="noreply@bpa-icr-ingest.example.com",
        to_emails=recipients.split(","),
        subject=subject,
        html_content=html_content,
    )
    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    logger.info("Sent email; status %s", response.status_code)


def upsert_icr(conn, df: pd.DataFrame) -> int:
    """
    Bulk upsert all rows in df into TARGET_TABLE.
    Returns number of rows affected.
    """
    if df.empty:
        return 0
    # Check and log problematic date values, and convert them to None
    date_columns = [
        'request_date', 'requested_in_service_date', 'agreed_to', 
        'feasibility_study', 'phase1_cluster_study', 'system_impact_study',
        'phase2_cluster_study', 'facilities_study'
    ]
    for col in date_columns:
        if col in df.columns:
            # Convert NaT/NaN values to None for PostgreSQL compatibility
            # Check for various types of NaT values
            df[col] = df[col].apply(lambda x: None if (
                pd.isna(x) or 
                str(x) == 'NaT' or 
                str(x) == 'nan' or 
                x is pd.NaT or
                (hasattr(x, 'value') and pd.isna(x.value))
            ) else x)
            # Additional safety check - replace any remaining NaT strings
            df[col] = df[col].replace('NaT', None)
            df[col] = df[col].replace('nan', None)
    tuples = [
        tuple([req] + [row[col] for col in df.columns])
        for req, row in df.iterrows()
    ]
    
    # Final safety check: Replace any remaining NaT values and truncate long strings
    cleaned_tuples = []
    for i, tup in enumerate(tuples):
        tup_list = list(tup)
        for j, val in enumerate(tup_list):
            # Handle NaT/nan values
            if str(val) == 'NaT' or str(val) == 'nan':
                if i < 5:  # Only log first 5 for debugging
                    logger.warning(f"Found NaT value at tuple {i}, position {j}: {val}")
                tup_list[j] = None
            # Truncate strings that are too long for VARCHAR(255) columns
            elif isinstance(val, str) and len(val) > 255:
                if i < 5:  # Only log first 5 for debugging
                    logger.warning(f"Truncating long string at tuple {i}, position {j}: {len(val)} chars")
                tup_list[j] = val[:255]
        cleaned_tuples.append(tuple(tup_list))
    tuples = cleaned_tuples
    cols = ", ".join(df.columns)
    placeholders = ", ".join(["%s"] * (1 + len(df.columns)))
    insert_cols = "request_number, " + cols
    updates = ", ".join(f"{col}=EXCLUDED.{col}" for col in df.columns)
    sql = f"""
      INSERT INTO {TARGET_TABLE} ({insert_cols})
      VALUES ({placeholders})
      ON CONFLICT (request_number)
      DO UPDATE
        SET {updates}
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, tuples)
        return cur.rowcount