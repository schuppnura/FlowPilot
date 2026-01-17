import { createApiClient } from './base';
import type {
  DelegationResponse,
  CreateDelegationRequest,
} from '../../types/models';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_DELEGATION_API_URL ||
  'https://flowpilot-delegation-api-737191827545.us-central1.run.app';

export class DelegationClient {
  private client;

  constructor(getToken: () => Promise<string | null>) {
    this.client = createApiClient(API_URL, getToken);
  }

  async createDelegation(
    request: CreateDelegationRequest
  ): Promise<DelegationResponse> {
    const response = await this.client.post<DelegationResponse>(
      '/v1/delegations',
      request
    );
    return response.data;
  }
}
