import sys
import json
import logging
import traceback
import os
from dotenv import load_dotenv

# This line will add the project's root folder to sys.path
sys.path.append(
    os.path.join(os.path.dirname(__file__), "../../")
)


# Now import the helper function - without the 'functions.' prefix
from factchecker.search.census_search import process_query

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set emulator flag, this tells our code that we're running it locally, regardless of
# whether we're using it or not
os.environ["FUNCTIONS_EMULATOR"] = "True"


def test_process_query():
    res = process_query(query="What is the weather?", use_llm=True)
    print(res)


if __name__ == "__main__":
    test_process_query()