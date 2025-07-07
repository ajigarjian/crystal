import subprocess
import sys
import os
import shutil
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
PROJECT_ID = "crystal-2f87e"  # Your GCP Project ID
REGION = "us-central1"        # The region for your function

# List of functions to deploy
# Format: (handler_module, function_name_in_code, desired_deployed_name, memory)
# handler_module is the python module path, e.g. 'energy_agent.energy_agent'
FUNCTIONS_TO_DEPLOY = [
    ("energy_agent.energy_agent", "energy_agent", "energy-agent", "512MB"),
    ("get_power_infra.get_power_infra", "get_power_infrastructure", "get-power-infrastructure", "512MB"),
    ("get_power_generators.get_power_generators", "get_power_generators", "get-power-generators", "512MB"),
    ("get_power_plants.get_power_plants", "get_power_plants", "get-power-plants", "512MB"),
]

GCP_CLI_PREFIX = "gcp-cli-"

# Files and folders to always include if present
ALWAYS_INCLUDE = [".env"]

# Helper: copy a file or directory
def copy_item(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

# --- Minimal requirements.txt logic ---
REQUIREMENTS_FILE = "requirements.txt"
IMPORT_RE = re.compile(r"^(?:from|import)\s+([a-zA-Z0-9_\.]+)")

# Map import names to PyPI package names if they differ (add more as needed)
IMPORT_TO_PYPI = {
    "dotenv": "python-dotenv",
    "psycopg2": "psycopg2-binary",
    "flask": "Flask",
    "sqlalchemy": "SQLAlchemy",
    "firebase_admin": "firebase-admin"
    # Add more mappings as needed
}

def parse_imports_from_file(pyfile):
    imports = set()
    with open(pyfile, "r") as f:
        for line in f:
            m = IMPORT_RE.match(line.strip())
            if m:
                root = m.group(1).split(".")[0]
                if root not in (".", "..", "__future__"):  # skip relative and __future__
                    imports.add(root)
    return imports

def collect_all_imports(build_dir):
    imports = set()
    for pyfile in Path(build_dir).rglob("*.py"):
        imports |= parse_imports_from_file(pyfile)
    return imports

def build_deploy_dir(handler_module):
    """
    Build a minimal deploy directory for the function.
    handler_module: e.g. 'energy_agent.energy_agent'
    Returns the path to the build directory.
    """
    build_temp_root = os.path.join(os.path.dirname(__file__), 'build_temp')
    if not os.path.exists(build_temp_root):
        os.makedirs(build_temp_root)

    build_dir = os.path.join(build_temp_root, f"build_{handler_module.replace('.', '_')}")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    # Copy handler module and its parent package
    parts = handler_module.split('.')
    if len(parts) > 1:
        # e.g. energy_agent.energy_agent -> copy energy_agent/
        top_dir = parts[0]
        copy_item(top_dir, os.path.join(build_dir, top_dir))
    else:
        # e.g. gcp_main -> copy gcp_main.py
        py_file = f"{handler_module}.py"
        copy_item(py_file, os.path.join(build_dir, py_file))

    # Copy helpers if needed
    if os.path.exists("helpers"):
        copy_item("helpers", os.path.join(build_dir, "helpers"))

    # Copy always-include files if present
    for fname in ALWAYS_INCLUDE:
        if os.path.exists(fname):
            copy_item(fname, os.path.join(build_dir, fname))

    return build_dir

def write_main_py(build_dir, handler_module, entry_point):
    """Generate a main.py that imports the entry point from the handler module."""
    main_py_content = f"from {handler_module} import {entry_point}\n"
    with open(os.path.join(build_dir, "main.py"), "w") as f:
        f.write(main_py_content)

def remove_build_dir(build_dir):
    try:
        shutil.rmtree(build_dir)
    except Exception:
        pass

def generate_requirements_with_pipreqs(build_dir):
    print(f"Generating requirements.txt with pipreqs in {build_dir} ...")
    result = subprocess.run([
        'pipreqs', build_dir, '--force', '--savepath', os.path.join(build_dir, 'requirements.txt')
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] pipreqs failed in {build_dir}:")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

def deploy_function(handler_module, entry_point, deployed_name, memory, project, region):
    """Deploys a single Cloud Function from a minimal build directory."""
    # Prefix the deployed function name
    deployed_name_with_prefix = f"{GCP_CLI_PREFIX}{deployed_name}"
    print(f"--- Deploying function '{deployed_name_with_prefix}' ---")

    build_dir = build_deploy_dir(handler_module)
    write_main_py(build_dir, handler_module, entry_point)

    # Generate minimal requirements.txt with pipreqs
    generate_requirements_with_pipreqs(build_dir)

    command = [
        "gcloud",
        "functions",
        "deploy",
        deployed_name_with_prefix,
        "--gen2",
        f"--project={project}",
        f"--region={region}",
        "--runtime=python311",
        f"--source={build_dir}",
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
            print(f"\n[ERROR] Deployment failed for {deployed_name_with_prefix} with exit code {process.returncode}.")
            return False
        else:
            print(f"\n[SUCCESS] Successfully deployed {deployed_name_with_prefix}.")
            return True

    except FileNotFoundError:
        print("\n[ERROR] `gcloud` command not found. Please ensure the Google Cloud SDK is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        return False
    finally:
        # Always remove build dir after deploy attempt
        remove_build_dir(build_dir)

def remove_build_temp_root():
    build_temp_root = os.path.join(os.path.dirname(__file__), 'build_temp')
    if os.path.exists(build_temp_root):
        try:
            shutil.rmtree(build_temp_root)
        except Exception:
            pass

def main():
    """Main function to deploy all configured Cloud Functions serially."""
    print("Starting deployment of Google Cloud Functions...")

    results = []
    try:
        for handler_module, entry_point, deployed_name, memory in FUNCTIONS_TO_DEPLOY:
            try:
                result = deploy_function(
                    handler_module, entry_point, deployed_name, memory, PROJECT_ID, REGION
                )
                results.append((handler_module, deployed_name, result))
            except Exception as exc:
                print(f"\n[ERROR] {deployed_name} generated an exception: {exc}")
                results.append((handler_module, deployed_name, False))

        success_count = sum(1 for _, _, r in results if r)
        failure_count = sum(1 for _, _, r in results if not r)

        print("\n--- Deployment Summary ---")
        print(f"Successfully deployed: {success_count}")
        print(f"Failed to deploy: {failure_count}")

        if failure_count > 0:
            print("\nSome deployments failed. Please check the logs above for details.")
            sys.exit(1)
        else:
            print("\nAll functions deployed successfully!")
    finally:
        remove_build_temp_root()

if __name__ == "__main__":
    main() 