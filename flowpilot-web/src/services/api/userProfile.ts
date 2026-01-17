import { createApiClient } from './base';
import type { TravelAgentUser } from '../../types/models';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_PERSONA_API_URL ||
  'https://flowpilot-persona-api-737191827545.us-central1.run.app';

interface UserInfo {
  sub: string;
  email?: string | null;
  persona: string;
}

interface ListUsersResponse {
  users: UserInfo[];
}

interface Persona {
  persona_id: string;
  user_sub: string;
  title: string;
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

  constructor(getToken: () => Promise<string | null>) {
    this.client = createApiClient(API_URL, getToken);
  }

  async listUsersByPersona(persona: string): Promise<TravelAgentUser[]> {
    console.log('UserProfileClient.listUsersByPersona: Fetching users with persona:', persona);
    try {
      const response = await this.client.get<ListUsersResponse>('/v1/users/by-persona', {
        params: { title: persona },
      });
      console.log('UserProfileClient.listUsersByPersona: Response:', response.data);
      console.log('UserProfileClient.listUsersByPersona: Raw users array:', response.data.users);
      
      // Map UserInfo to TravelAgentUser format and filter out users without email
      const result = response.data.users
        .filter((user) => user.email && user.email.trim().length > 0) // Only include users with valid email
        .map((user) => ({
          id: user.sub,
          username: user.email?.split('@')[0] || '',
          email: user.email || undefined,
          displayName: user.email || '', // Use email for display, never show sub
        }));
      
      console.log('UserProfileClient.listUsersByPersona: Returning', result.length, 'users after filtering');
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

  async listPersonas(): Promise<string[]> {
    console.log('UserProfileClient.listPersonas: Fetching user personas');
    const response = await this.client.get<ListPersonasResponse>('/v1/personas');
    console.log('UserProfileClient.listPersonas: Response:', response.data);
    // Extract persona titles from the response and deduplicate
    const titles = response.data.personas
      .filter((p) => p.status === 'active')
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
