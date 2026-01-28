// Type definitions matching the Swift app's Models.swift

export interface WorkflowTemplate {
  template_id: string;
  domain: string;
  name: string;
  id: string; // Computed from template_id
}

export interface Workflow {
  workflow_id: string;
  template_id: string;
  owner_sub: string;
  created_at: string;
  departure_date?: string;
  item_count: number;
  id: string; // Computed from workflow_id
}

export interface WorkflowItem {
  item_id: string;
  workflow_item_id?: string; // Alternative field name
  kind: string;
  title: string;
  status: string;
  type?: string;
  city?: string;
  neighborhood?: string;
  star_rating?: number;
  cuisine?: string;
  departure_airport?: string;
  arrival_airport?: string;
  id: string; // Computed from item_id or workflow_item_id
}

export interface TravelAgentUser {
  id: string;
  username: string;
  email?: string;
  displayName?: string; // Computed from username if not provided
}

export interface CreateDelegationRequest {
  principal_id: string;
  delegate_id: string;
  workflow_id?: string;
  scope?: string[];
  expires_in_days: number;
}

export interface DelegationResponse {
  principal_id: string;
  delegate_id: string;
  workflow_id?: string;
  scope: string[];
  expires_at: string;
  delegation_id?: string;
}

export interface AgentRunRequest {
  workflow_id: string;
  principal_sub: string;
  dry_run: boolean;
  persona?: string;
}

export interface CreateWorkflowRequest {
  template_id: string;
  principal_sub: string;
  start_date: string;
  persona?: string;
  domain?: string;
}

export interface AgentRunResponse {
  run_id: string;
  workflow_id: string;
  principal_sub: string;
  dry_run: boolean;
  results: AgentRunItemResult[];
}

export interface AgentRunItemResult {
  workflow_item_id: string;
  kind: string;
  status: string;
  decision: string;
  reason_codes?: string[];
  advice?: Advice[];
  id: string; // Computed from workflow_item_id
}

export interface Advice {
  type: string;
  message: string;
}
