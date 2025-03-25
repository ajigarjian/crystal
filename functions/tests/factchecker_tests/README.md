Use this directly to directly invoke individual functions from factchecker. It is strongly recommended to test each function direclty here before proceeding to integrate it into `stream_search_datasets` or deploying an entirely new Cloud Function.

Use `test_pinecone_search` as a basis.

### Postgres
-> Need to write a new test function invoking Postgres?

1. (One time) Run `gcloud auth application-default set-quota-project crystal-2f87e` to set the GCP project ID
1. Need Postgres? Head over to `scripts/sql` and run this command to make a connection to our Postgres SQL server:
`./cloud-sql-proxy --address 0.0.0.0 --port 1234 crystal-2f87e:us-east4:crystal-sql`

Once the proxy is running, you'll need to pass the emulator flag with the Cloud SQL proxy running so we know to access the proxy'd DB and not try to access the real (unreachable) one. See `test_pinecone_search` for examples, or just regard this sample:

```
from dotenv import load_dotenv
# This line will add the project's root folder to sys.path
sys.path.append(
    os.path.join(os.path.dirname(__file__), "../../")
)

# Import the search functions
from factchecker.search.pinecone_search import vector_search_datasets_pinecone
from factchecker.search.search_utils import generate_similar_queries, parallel_search, single_search

load_dotenv()
# Set emulator flag for local testing
os.environ["FUNCTIONS_EMULATOR"] = "True"

# Set up local database connection for testing
os.environ["DB_HOST"] = os.getenv("DB_HOST", "localhost")
os.environ["DB_PORT"] = os.getenv("DB_PORT", "1234")
os.environ["DB_USER"] = os.getenv("DB_USER", "postgres")
os.environ["DB_PASSWORD"] = os.getenv("DB_PASSWORD", "")
os.environ["DB_NAME"] = os.getenv("DB_NAME", "crystal")
# Unset Cloud SQL connection if it exists
if "INSTANCE_CONNECTION_NAME" in os.environ:
    del os.environ["INSTANCE_CONNECTION_NAME"]
```