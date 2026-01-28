/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FIREBASE_API_KEY: string
  readonly VITE_FIREBASE_AUTH_DOMAIN: string
  readonly VITE_FIREBASE_PROJECT_ID: string
  readonly VITE_DOMAIN_SERVICES_API_URL: string
  readonly VITE_DELEGATION_API_URL: string
  readonly VITE_AI_AGENT_API_URL: string
  readonly VITE_AUTHZ_API_URL: string
  readonly VITE_PERSONA_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
