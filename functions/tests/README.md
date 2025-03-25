Use this directory to test backend code that you want to move into main.py and deploy as a Firebase cloud function.

-> E.g. wanting to make a change to stream_search_datasets?

1. Run `firebase emulators:start` in case you need Firestore.
1. (One time) Run `gcloud auth application-default set-quota-project crystal-2f87e` to set the GCP project ID
1. Need Postgres? Head over to `scripts/sql` and run this command to make a connection to our Postgres SQL server:
`./cloud-sql-proxy --address 0.0.0.0 --port 1234 crystal-2f87e:us-east4:crystal-sql`
1. Head over to functions/tests and run `test_stream_search_datasets.py`
1. Make changes to the dependencies imported by the stream_search_datasets in all of the subfiles in factchecker as desired. If applicable, test each sub-function inside their own modules.
1. When satisfied, make changes to the corresponding function in `main.py`.
1. Test function execution over in `tests/functions/test_FUNCTION.py` and ensure the Firebase function works as intended.
1. Test in the frontend locally (if applicable)
1. When satisfied with the changes, deploy: `firebase deploy` from the project root.
