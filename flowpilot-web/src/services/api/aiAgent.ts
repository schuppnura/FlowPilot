import { createApiClient } from './base';
import type { AgentRunResponse, AgentRunRequest } from '../../types/models';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_AI_AGENT_API_URL ||
  'https://flowpilot-ai-agent-api-737191827545.us-central1.run.app';

export class AIAgentClient {
  private client;

  constructor(getToken: () => Promise<string | null>) {
    this.client = createApiClient(API_URL, getToken);
  }

  async runAgent(request: AgentRunRequest): Promise<AgentRunResponse> {
    const response = await this.client.post<AgentRunResponse>(
      '/v1/agent-runs',
      request
    );
    return response.data;
  }
}
