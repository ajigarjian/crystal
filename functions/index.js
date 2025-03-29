// For HTTP functions, add a timeout parameter when creating the function
exports.yourHttpFunction = functions
  .region('us-central1')
  .runWith({
    timeoutSeconds: 300,  // Increase timeout to 300 seconds (5 minutes)
  })
  .https.onRequest((req, res) => {
    // ... your function code ...
  }); 

// For background functions
exports.streamSearchDatasets = functions
  .region('us-central1')
  .runWith({
    timeoutSeconds: 300,  // Increase timeout to 300 seconds (5 minutes)
  })
  .firestore
  .document('path/to/document')
  .onWrite((change, context) => {
    // ... your function code ...
  }); 