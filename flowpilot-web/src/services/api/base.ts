import axios, { AxiosInstance, AxiosError } from 'axios';

export class ApiClientError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public body?: string
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

export function createApiClient(
  baseURL: string,
  getToken: () => Promise<string | null>,
  onAuthError?: () => void
): AxiosInstance {
  const client = axios.create({
    baseURL,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Add token to requests
  client.interceptors.request.use(async (config) => {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Handle errors
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response) {
        const statusCode = error.response.status;
        const body = typeof error.response.data === 'string' 
          ? error.response.data 
          : JSON.stringify(error.response.data);
        
        // Check for 403 authentication error
        if (statusCode === 403 && onAuthError) {
          const responseData = error.response.data as any;
          if (responseData?.detail === 'Not authenticated') {
            onAuthError();
          }
        }
        
        throw new ApiClientError(
          `HTTP error ${statusCode}: ${body}`,
          statusCode,
          body
        );
      } else if (error.request) {
        // Network error - could be CORS, connection refused, etc.
        const url = error.config?.url || 'unknown';
        const baseURL = error.config?.baseURL || 'unknown';
        const fullUrl = baseURL !== 'unknown' && url !== 'unknown' 
          ? `${baseURL}${url}` 
          : 'unknown URL';
        console.error('Network error details:', {
          message: error.message,
          code: error.code,
          url: fullUrl,
          baseURL: error.config?.baseURL,
          method: error.config?.method,
        });
        throw new ApiClientError(
          `Network error: ${error.message || 'Failed to connect to server'}. URL: ${fullUrl}. This may be a CORS issue.`
        );
      } else {
        throw new ApiClientError(`Request error: ${error.message}`);
      }
    }
  );

  return client;
}
