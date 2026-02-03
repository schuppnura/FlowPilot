import { createApiClient } from './base';
import type { TravelAgentUser } from '../../types/models';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_PERSONA_API_URL ||
  'https://flowpilot-persona-api-737191827545.europe-west1.run.app';

// Response from /v1/users endpoint
interface UserInfo {
  id: string;  // User sub/uid
  username: string;  // Display name or email or uid
  email?: string | null;  // Optional email (may be empty)
}

// Response from /v1/users/by-persona endpoint (legacy format)
interface UserInfoByPersona {
  sub: string;
  email?: string | null;
  persona: string;
}

interface ListUsersResponse {
  users: UserInfo[];
}

interface ListUsersByPersonaResponse {
  users: UserInfoByPersona[];
}

interface Persona {
  persona_id: string;
  user_sub: string;
  title: string;
  circle: string;
  scope: string[];
  status: string;
  valid_from: string;
  valid_till: string;
  consent: boolean;
  autobook_price: number;
  autobook_leadtime: number;
  autobook_risklevel: number;
}

interface ListPersonasResponse {
  personas: Persona[];
}


export class UserProfileClient {
  private client;

  constructor(
    getToken: () => Promise<string | null>,
    onAuthError?: () => void
  ) {
    this.client = createApiClient(API_URL, getToken, onAuthError);
  }

  async listUsersByPersona(persona: string): Promise<TravelAgentUser[]> {
    console.log('UserProfileClient.listUsersByPersona: Fetching users with persona:', persona);
    try {
      const response = await this.client.get<ListUsersByPersonaResponse>('/v1/users/by-persona', {
        params: { title: persona },
      });
      console.log('UserProfileClient.listUsersByPersona: Response:', response.data);
      console.log('UserProfileClient.listUsersByPersona: Raw users array:', response.data.users);
      
      // Map UserInfoByPersona to TravelAgentUser format
      const result = response.data.users.map((user) => ({
        id: user.sub,
        username: user.email?.split('@')[0] || user.sub,
        email: user.email || undefined,
        displayName: user.email || user.sub,
      }));
      
      console.log('UserProfileClient.listUsersByPersona: Returning', result.length, 'users');
      return result;
    } catch (error: any) {
      console.error('UserProfileClient.listUsersByPersona: ERROR:', error);
      console.error('UserProfileClient.listUsersByPersona: Error details:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status,
      });
      throw error;
    }
  }

  async listAllUsers(): Promise<TravelAgentUser[]> {
    console.log('UserProfileClient.listAllUsers: Fetching all users');
    try {
      const response = await this.client.get<ListUsersResponse>('/v1/users');
      console.log('UserProfileClient.listAllUsers: Response:', response.data);
      
      // Map UserInfo to TravelAgentUser format - include all users
      const result = response.data.users.map((user) => ({
        id: user.id,
        username: user.username,
        email: user.email || undefined,
        displayName: user.username,  // Use username (which prioritizes display name over email)
      }));
      
      console.log('UserProfileClient.listAllUsers: Returning', result.length, 'users');
      return result;
    } catch (error: any) {
      console.error('UserProfileClient.listAllUsers: ERROR:', error);
      throw error;
    }
  }

  async listPersonas(): Promise<string[]> {
    console.log('UserProfileClient.listPersonas: Fetching user personas');
    const response = await this.client.get<ListPersonasResponse>('/v1/personas');
    console.log('UserProfileClient.listPersonas: Response:', response.data);
    // Extract persona titles from the response and deduplicate
    // NOTE: Include all personas regardless of status - PEP/PDP will validate if they're valid for operations
    const titles = response.data.personas
      .map((p) => p.title);
    // Remove duplicates using Set
    return Array.from(new Set(titles));
  }

  async getPersonasDetailed(status?: string): Promise<Persona[]> {
    console.log('UserProfileClient.getPersonasDetailed: Fetching detailed personas', { status });
    const params = status ? { status } : {};
    const response = await this.client.get<ListPersonasResponse>('/v1/personas', { params });
    console.log('UserProfileClient.getPersonasDetailed: Response:', response.data);
    return response.data.personas;
  }

  async getPersonaById(personaId: string): Promise<Persona> {
    console.log('UserProfileClient.getPersonaById: Fetching persona', personaId);
    const response = await this.client.get<Persona>(`/v1/personas/${personaId}`);
    return response.data;
  }

  async updatePersona(personaId: string, updates: Partial<Persona>): Promise<Persona> {
    console.log('UserProfileClient.updatePersona: Updating persona', personaId, updates);
    const response = await this.client.put<Persona>(`/v1/personas/${personaId}`, updates);
    return response.data;
  }

  async createPersona(personaData: Omit<Persona, 'persona_id' | 'user_sub' | 'created_at' | 'updated_at'>): Promise<Persona> {
    console.log('UserProfileClient.createPersona: Creating persona', personaData);
    const response = await this.client.post<Persona>('/v1/personas', personaData);
    return response.data;
  }

  async deletePersona(personaId: string): Promise<void> {
    console.log('UserProfileClient.deletePersona: Deleting persona', personaId);
    await this.client.delete(`/v1/personas/${personaId}`);
  }
}
