import subprocess
import sys

# --- Configuration ---
PROJECT_ID = "crystal-2f87e"  # Your GCP Project ID
REGION = "us-central1"        # The region for your function

# List of functions to deploy from gcp_main.py
# Format: (function_name_in_code, desired_deployed_name, memory)
FUNCTIONS_TO_DEPLOY = [
    ("energy_agent", "energy-agent", "512MB"),
    ("hello_world", "hello-world", "128MB"),
]

def deploy_function(entry_point, deployed_name, memory, project, region):
    """Deploys a single Cloud Function."""
    print(f"--- Deploying function '{deployed_name}' ---")
    
    command = [
        "gcloud",
        "functions",
        "deploy",
        deployed_name,
        "--gen2",
        f"--project={project}",
        f"--region={region}",
        "--runtime=python311",
        "--source=.",
        f"--entry-point={entry_point}",
        f"--memory={memory}",
        "--trigger-http",
        "--allow-unauthenticated",
        f"--vpc-connector=projects/{project}/locations/{region}/connectors/crystal-connector"
    ]
    
    print(f"Executing command: {' '.join(command)}")
    
    try:
        # Execute the command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Stream the output
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                
        # Check for errors
        if process.returncode != 0:
            print(f"\n[ERROR] Deployment failed for {deployed_name} with exit code {process.returncode}.")
            return False
        else:
            print(f"\n[SUCCESS] Successfully deployed {deployed_name}.")
            return True
            
    except FileNotFoundError:
        print("\n[ERROR] `gcloud` command not found. Please ensure the Google Cloud SDK is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        return False

def main():
    """Main function to deploy all configured Cloud Functions."""
    print("Starting deployment of Google Cloud Functions...")
    
    success_count = 0
    failure_count = 0
    
    for entry_point, deployed_name, memory in FUNCTIONS_TO_DEPLOY:
        if deploy_function(entry_point, deployed_name, memory, PROJECT_ID, REGION):
            success_count += 1
        else:
            failure_count += 1
            
    print("\n--- Deployment Summary ---")
    print(f"Successfully deployed: {success_count}")
    print(f"Failed to deploy: {failure_count}")
    
    if failure_count > 0:
        print("\nSome deployments failed. Please check the logs above for details.")
        sys.exit(1)
    else:
        print("\nAll functions deployed successfully!")

if __name__ == "__main__":
    main() 