import React, { createContext, useContext, useEffect, useState } from 'react';
import { User, onAuthStateChanged } from 'firebase/auth';
import { auth, signIn, signUp, logout, getCurrentToken } from '../services/firebase/auth';
import { getAccessToken, clearAccessToken } from '../services/auth/tokenExchange';

interface AuthContextType {
  user: User | null;
  idToken: string | null;  // Firebase ID token (for UI display only)
  loading: boolean;
  showSignInModal: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  openSignInModal: () => void;
  closeSignInModal: () => void;
  getToken: () => Promise<string | null>;  // Returns pseudonymous access token for API calls
  getIdToken: () => Promise<string | null>;  // Returns Firebase ID token for UI display
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSignInModal, setShowSignInModal] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setUser(user);
      if (user) {
        // Force refresh to get latest custom claims (persona) when auth state changes
        const token = await user.getIdToken(true);
        setIdToken(token);
      } else {
        setIdToken(null);
      }
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  const handleSignIn = async (email: string, password: string) => {
    const { user, idToken } = await signIn(email, password);
    setUser(user);
    setIdToken(idToken);
    setShowSignInModal(false);  // Close modal after successful sign-in
  };

  const handleSignUp = async (email: string, password: string) => {
    const { user, idToken } = await signUp(email, password);
    setUser(user);
    setIdToken(idToken);
    setShowSignInModal(false);  // Close modal after successful sign-up
  };

  const handleSignOut = async () => {
    await logout();
    clearAccessToken();  // Clear cached access token
    setUser(null);
    setIdToken(null);
  };

  const getToken = async () => {
    // Return pseudonymous access token for API calls (contains only sub)
    return await getAccessToken();
  };

  const getIdToken = async () => {
    // Return Firebase ID token for UI personalization (contains email, name, etc.)
    if (user) {
      const token = await getCurrentToken();
      setIdToken(token || null);
      return token;
    }
    return null;
  };

  const value: AuthContextType = {
    user,
    idToken,
    loading,
    showSignInModal,
    signIn: handleSignIn,
    signUp: handleSignUp,
    signOut: handleSignOut,
    openSignInModal: () => setShowSignInModal(true),
    closeSignInModal: () => setShowSignInModal(false),
    getToken,
    getIdToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
