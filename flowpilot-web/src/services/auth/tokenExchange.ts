import { auth } from '../firebase/config';

const AUTHZ_API_URL = import.meta.env.VITE_AUTHZ_API_URL || 
  'https://flowpilot-authz-api-3rytlurg2a-ew.a.run.app';

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * Exchange Firebase ID token for pseudonymous FlowPilot access token.
 * 
 * This separates authentication (Firebase ID token with PII for UI display)
 * from authorization (pseudonymous access token for API calls).
 * 
 * The Firebase ID token contains email, name, etc. and is used only client-side for UI.
 * The FlowPilot access token contains only the user's UUID (sub) and is used for all API calls.
 */
export async function exchangeToken(): Promise<AccessTokenResponse> {
  const user = auth.currentUser;
  if (!user) {
    throw new Error('No authenticated user');
  }
  
  // Get Firebase ID token
  const idToken = await user.getIdToken(true);
  
  // Exchange for pseudonymous access token
  const response = await fetch(`${AUTHZ_API_URL}/v1/token/exchange`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${idToken}`,  // Firebase ID token for authentication
    },
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Token exchange failed: ${response.status} ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Get current access token with automatic refresh.
 * 
 * Caches access token and automatically exchanges when expired.
 * This is the primary function used by API clients to get authorization tokens.
 */
let cachedAccessToken: string | null = null;
let accessTokenExpiry: number = 0;

export async function getAccessToken(): Promise<string | null> {
  const user = auth.currentUser;
  if (!user) {
    cachedAccessToken = null;
    accessTokenExpiry = 0;
    return null;
  }
  
  // Return cached token if still valid (with 60s buffer to avoid race conditions)
  const now = Date.now() / 1000;
  if (cachedAccessToken && accessTokenExpiry > now + 60) {
    return cachedAccessToken;
  }
  
  // Exchange for new access token
  try {
    const response = await exchangeToken();
    cachedAccessToken = response.access_token;
    accessTokenExpiry = now + response.expires_in;
    return cachedAccessToken;
  } catch (error) {
    console.error('[TokenExchange] Failed to exchange token:', error);
    cachedAccessToken = null;
    accessTokenExpiry = 0;
    return null;
  }
}

/**
 * Clear cached access token (e.g., on logout or token invalidation)
 */
export function clearAccessToken(): void {
  cachedAccessToken = null;
  accessTokenExpiry = 0;
}
