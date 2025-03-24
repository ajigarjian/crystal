import { initializeApp } from "firebase/app";
import { getFunctions, httpsCallable, connectFunctionsEmulator } from "firebase/functions";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "AIzaSyC3KIK0ol5TquNaz6-DyVoxzijDNySgrq4",
    authDomain: "crystal-2f87e.firebaseapp.com",
    projectId: "crystal-2f87e",
    storageBucket: "crystal-2f87e.firebasestorage.app",
    messagingSenderId: "422374862387",
    appId: "1:422374862387:web:1a11af2b205c777173bd46",
    measurementId: "G-1CFM4WMH4B"
  };

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Cloud Firestore and get a reference to the service
export const db = getFirestore(app);

// Initialize Cloud Functions
export const functions = getFunctions(app);

// Set up emulator if in development
if (process.env.NODE_ENV === 'development') {
  console.log(`Using Firebase Functions emulator...`);
  connectFunctionsEmulator(functions, 'localhost', 5001);
  connectFirestoreEmulator(db, 'localhost', 8080);
}

// Export a helper for calling the waitlist registration function
export const registerWaitlist = async (data: { email: string, first_name: string }) => {
  const registerWaitlistFunction = httpsCallable(functions, 'register_waitlist');
  
  try {
    const result = await registerWaitlistFunction(data);
    return result;
  } catch (error: any) {
    console.error('Error calling register_waitlist:', error);
    throw new Error(error.message || 'Failed to register');
  }
}; 