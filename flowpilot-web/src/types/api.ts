// API response types

export interface ApiError {
  message: string;
  code?: string;
}

export interface CreateWorkflowRequest {
  template_id: string;
  principal_sub: string;
  start_date: string;
  persona?: string;
}
