import { createApiClient, ApiClientError } from './base';
import type {
  WorkflowTemplate,
  Workflow,
  WorkflowItem,
} from '../../types/models';
import type { CreateWorkflowRequest } from '../../types/models';
import { config } from '../../config';

// Use direct URL (CORS is now enabled on the API)
const API_URL =
  import.meta.env.VITE_DOMAIN_SERVICES_API_URL ||
  'https://flowpilot-domain-services-api-3rytlurg2a-ew.a.run.app';

interface WorkflowTemplatesResponse {
  templates: WorkflowTemplate[];
}

interface WorkflowsResponse {
  workflows: Workflow[];
}

interface WorkflowItemsResponse {
  items: WorkflowItem[];
}

export class DomainServicesClient {
  private client;

  constructor(
    getToken: () => Promise<string | null>,
    onAuthError?: () => void
  ) {
    this.client = createApiClient(API_URL, getToken, onAuthError);
  }

  async fetchTemplates(): Promise<WorkflowTemplate[]> {
    const response = await this.client.get<WorkflowTemplatesResponse>(
      '/v1/workflow-templates'
    );
    return response.data.templates;
  }

  async fetchWorkflows(): Promise<Workflow[]> {
    const response = await this.client.get<WorkflowsResponse>('/v1/workflows');
    return response.data.workflows;
  }

  async fetchWorkflowItems(
    workflowId: string,
    personaTitle?: string,
    personaCircle?: string
  ): Promise<WorkflowItem[]> {
    const params: Record<string, string> = {};
    if (personaTitle) {
      params.persona_title = personaTitle;
      // Include persona_circle only if it has a value
      if (personaCircle !== undefined && personaCircle !== null) {
        params.persona_circle = personaCircle;
      }
    }
    const response = await this.client.get<WorkflowItemsResponse>(
      `/v1/workflows/${workflowId}/items`,
      { params }
    );
    return response.data.items;
  }

  async createWorkflow(
    request: CreateWorkflowRequest
  ): Promise<string> {
    // Include domain from config if not already specified
    const enrichedRequest = {
      ...request,
      domain: request.domain || config.domain,
    };
    const response = await this.client.post('/v1/workflows', enrichedRequest);
    
    // Extract workflow_id from response (can be top-level or nested)
    const data = response.data;
    if (data.workflow_id) {
      return data.workflow_id;
    }
    if (data.trip?.workflow_id) {
      return data.trip.workflow_id;
    }
    
    throw new ApiClientError('Invalid response: workflow_id not found');
  }
}
