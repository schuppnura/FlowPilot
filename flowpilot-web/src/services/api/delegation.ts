import { createApiClient } from './base';
import type {
  DelegationResponse,
  CreateDelegationRequest,
} from '../../types/models';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_DELEGATION_API_URL ||
  'https://flowpilot-delegation-api-3rytlurg2a-ew.a.run.app';

export class DelegationClient {
  private client;

  constructor(
    getToken: () => Promise<string | null>,
    onAuthError?: () => void
  ) {
    this.client = createApiClient(API_URL, getToken, onAuthError);
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

  async fetchDelegations(principalId: string): Promise<DelegationResponse[]> {
    const response = await this.client.get<{ delegations: DelegationResponse[] }>(
      `/v1/delegations?principal_id=${principalId}`
    );
    return response.data.delegations;
  }

  async revokeDelegation(delegation: DelegationResponse): Promise<void> {
    // API expects principal_id, delegate_id, and workflow_id in request body
    console.log('DelegationClient.revokeDelegation: Called with delegation:', delegation);
    const requestData = {
      principal_id: delegation.principal_id,
      delegate_id: delegation.delegate_id,
      workflow_id: delegation.workflow_id || null,
    };
    console.log('DelegationClient.revokeDelegation: Sending DELETE request with data:', requestData);
    
    try {
      await this.client.delete('/v1/delegations', {
        data: requestData
      });
      console.log('DelegationClient.revokeDelegation: DELETE request succeeded');
    } catch (error) {
      console.error('DelegationClient.revokeDelegation: DELETE request failed:', error);
      throw error;
    }
  }
}
