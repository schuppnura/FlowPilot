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
  password: string
) {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  const idToken = await userCredential.user.getIdToken();
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
