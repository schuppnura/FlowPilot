import { createApiClient } from './base';

const API_URL =
  import.meta.env.VITE_AUTHZ_API_URL ||
  'https://flowpilot-authz-api-3rytlurg2a-ew.a.run.app';

interface Advice {
  type: string;
  message: string;
}

interface ValidatePersonaRequest {
  subject: {
    type: string;
    id: string;
    properties: {
      persona: string;
    };
  };
  action: {
    name: string;
  };
  resource: {
    type: string;
    id: string;
  };
  context: {
    principal: {
      id: string;
      persona?: string;
      persona_status?: string;
      persona_valid_from?: string;
      persona_valid_till?: string;
    };
    policy_hint?: string;
  };
  options?: {
    dry_run?: boolean;
    explain?: boolean;
  };
}

interface ValidatePersonaResponse {
  decision: 'allow' | 'deny';
  reason_codes: string[];
  advice: Advice[];
}

export class AuthZClient {
  private client;

  constructor(
    getToken: () => Promise<string | null>,
    onAuthError?: () => void
  ) {
    this.client = createApiClient(API_URL, getToken, onAuthError);
  }

  /**
   * Check if a user has a valid active persona.
   * This calls the authz-api which evaluates the OPA policy.
   * 
   * @param principalId User's sub/uid
   * @param personaTitle Persona title to validate
   * @param personaMetadata Persona metadata (status, valid_from, valid_till)
   * @returns Promise<ValidatePersonaResponse>
   */
  async validatePersona(
    principalId: string,
    personaTitle: string,
    personaMetadata: {
      status: string;
      valid_from: string;
      valid_till: string;
    }
  ): Promise<ValidatePersonaResponse> {
    console.log('AuthZClient.validatePersona: Validating persona', {
      principalId,
      personaTitle,
      personaMetadata,
    });

    const request: ValidatePersonaRequest = {
      subject: {
        type: 'user',
        id: principalId,
        properties: {
          persona: personaTitle,
        },
      },
      action: {
        name: 'validate_persona',
      },
      resource: {
        type: 'persona',
        id: `persona:${principalId}:${personaTitle}`,
      },
      context: {
        principal: {
          id: principalId,
          persona: personaTitle,
          persona_status: personaMetadata.status,
          persona_valid_from: personaMetadata.valid_from,
          persona_valid_till: personaMetadata.valid_till,
        },
        policy_hint: import.meta.env.VITE_DOMAIN || 'travel',
      },
      options: {
        dry_run: true,
        explain: true,
      },
    };

    try {
      const response = await this.client.post<ValidatePersonaResponse>(
        '/v1/evaluate',
        request
      );
      console.log('AuthZClient.validatePersona: Response:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('AuthZClient.validatePersona: ERROR:', error);
      throw error;
    }
  }
}
