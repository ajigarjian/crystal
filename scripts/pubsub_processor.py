#!/usr/bin/env python3
import os
import time
import json
import requests
import pandas as pd
import psycopg2
from google.cloud import pubsub_v1
from concurrent.futures import TimeoutError

# Configuration
PROJECT_ID = "crystal-2f87e"  # Your project ID
SUBSCRIPTION_ID = "resource-processor-sub"
DB_HOST = "YOUR_CLOUD_SQL_IP"  # Replace with your Cloud SQL IP
DB_USER = "postgres"
DB_PASSWORD = "YOUR_SECURE_PASSWORD"
DB_NAME = "processed_resources"
DOWNLOAD_DIR = "/tmp/downloads"
PARQUET_DIR = "/home/processed_data"

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(PARQUET_DIR, exist_ok=True)

# Initialize Pub/Sub subscriber
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

# Database connection function
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Update database function
def update_database(original_url, parquet_path, original_size, compressed_size):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
        
        query = """
        INSERT INTO processed_files 
        (original_resource_url, compressed_path, size_bytes, compression_ratio) 
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (original_url, parquet_path, compressed_size, compression_ratio))
        conn.commit()
        print(f"Database updated for {original_url}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database update error: {e}")

# Process message function
def process_message(message):
    try:
        data = json.loads(message.data.decode('utf-8'))
        resource_url = data.get('resource_url')
        
        if not resource_url:
            print("No resource URL in message, acknowledging and skipping")
            message.ack()
            return
        
        print(f"Processing resource: {resource_url}")
        
        # Download the resource
        local_filename = os.path.join(DOWNLOAD_DIR, os.path.basename(resource_url))
        response = requests.get(resource_url, stream=True)
        response.raise_for_status()
        
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        original_size = os.path.getsize(local_filename)
        print(f"Downloaded {local_filename}, size: {original_size} bytes")
        
        # Convert to Parquet (assuming CSV for this example, modify as needed)
        try:
            # We'll try to detect the file type and process accordingly
            if local_filename.endswith('.csv'):
                df = pd.read_csv(local_filename)
            elif local_filename.endswith('.json'):
                df = pd.read_json(local_filename)
            elif local_filename.endswith('.xlsx') or local_filename.endswith('.xls'):
                df = pd.read_excel(local_filename)
            else:
                # For unsupported formats, we'll just read as text and create a DataFrame
                with open(local_filename, 'r') as text_file:
                    content = text_file.read()
                df = pd.DataFrame({'content': [content]})
            
            # Create parquet filename
            parquet_filename = os.path.splitext(os.path.basename(local_filename))[0] + '.parquet'
            parquet_path = os.path.join(PARQUET_DIR, parquet_filename)
            
            # Write to parquet with compression
            df.to_parquet(parquet_path, compression='snappy')
            
            compressed_size = os.path.getsize(parquet_path)
            print(f"Converted to Parquet: {parquet_path}, size: {compressed_size} bytes")
            
            # Update database
            update_database(resource_url, parquet_path, original_size, compressed_size)
            
            # Clean up downloaded file
            os.remove(local_filename)
            print(f"Cleaned up {local_filename}")
            
            # Acknowledge the message
            message.ack()
            print(f"Successfully processed {resource_url}")
            
        except Exception as e:
            print(f"Error processing file {local_filename}: {e}")
            message.nack()  # Negative acknowledgment to retry
    
    except Exception as e:
        print(f"Error processing message: {e}")
        message.nack()  # Negative acknowledgment to retry

# Callback for Pub/Sub messages
def callback(message):
    print(f"Received message: {message}")
    process_message(message)

# Main function to start the subscriber
def main():
    print(f"Listening for messages on {subscription_path}...")
    streaming_pull_future = subscriber.subscribe(
        subscription_path, callback=callback
    )

    try:
        # Keep the main thread alive to receive messages
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Stopping subscriber...")
        streaming_pull_future.cancel()
        streaming_pull_future.result()

if __name__ == "__main__":
    main()