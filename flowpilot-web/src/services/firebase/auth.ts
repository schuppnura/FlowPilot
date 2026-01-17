import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  User,
} from 'firebase/auth';
import { auth } from './config';

export { auth };

export interface PersonaAttributes {
  consent: boolean;
  autobook_price: number;
  autobook_leadtime: number;
  autobook_risklevel: number;
}

export async function signIn(email: string, password: string) {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  // Force refresh to get latest custom claims (persona)
  const idToken = await userCredential.user.getIdToken(true);
  return { user: userCredential.user, idToken };
}

export async function signUp(
  email: string,
  password: string,
  persona: string,
  personaAttrs: PersonaAttributes
) {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  
  // Create persona via user-profile API POST /v1/personas
  try {
    const initialToken = await userCredential.user.getIdToken();
    const userProfileApiUrl = import.meta.env.VITE_PERSONA_API_URL || 
      'https://flowpilot-persona-api-737191827545.us-central1.run.app';
    
    // Calculate validity dates (current date to +1 year)
    const now = new Date();
    const oneYearLater = new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000);
    
    const response = await fetch(`${userProfileApiUrl}/v1/personas`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${initialToken}`,
      },
      body: JSON.stringify({
        title: persona,
        scope: ['read', 'execute'],
        valid_from: now.toISOString(),
        valid_till: oneYearLater.toISOString(),
        consent: personaAttrs.consent,
        autobook_price: personaAttrs.autobook_price,
        autobook_leadtime: personaAttrs.autobook_leadtime,
        autobook_risklevel: personaAttrs.autobook_risklevel,
      }),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Failed to create persona:', response.status, errorText);
      throw new Error(`Failed to create persona: ${errorText}`);
    }
    
    const personaData = await response.json();
    console.log('Successfully created persona:', personaData);
  } catch (error) {
    console.error('Error creating persona:', error);
    // Delete the Firebase user if persona creation fails
    await userCredential.user.delete();
    throw error;
  }
  
  // Force refresh to get latest token
  const idToken = await userCredential.user.getIdToken(true);
  return { user: userCredential.user, idToken };
}

export async function logout() {
  await firebaseSignOut(auth);
}

export async function getCurrentToken(forceRefresh: boolean = false): Promise<string | null> {
  const user = auth.currentUser;
  if (!user) return null;
  return await user.getIdToken(forceRefresh);
}

export function getCurrentUser(): User | null {
  return auth.currentUser;
}
