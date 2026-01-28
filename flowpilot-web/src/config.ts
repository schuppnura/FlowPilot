// FlowPilot Domain Configuration
// This determines which policy domain (travel, nursing, etc.) the web app targets

export type AppDomain = 'travel' | 'nursing';

// Domain-specific terminology and styling
interface DomainConfig {
  displayName: string;
  tagline: string;
  backgroundImage: string;
  terminology: {
    workflow: string;
    workflows: string;
    workflowItem: string;
    workflowItems: string;
    createAction: string; // e.g., "Create New Trip" or "Create Work Schedule"
    manageAction: string; // e.g., "Manage My Trip" or "Manage My Schedule"
    myWorkflows: string; // e.g., "My Trips" or "My Schedules"
  };
}

const domainConfigs: Record<AppDomain, DomainConfig> = {
  travel: {
    displayName: 'Travel',
    tagline: 'Policy-driven authorization & delegation for AI-powered workflows',
    backgroundImage: '/images/nura-home.jpg',
    terminology: {
      workflow: 'itinerary',
      workflows: 'itineraries',
      workflowItem: 'trip item',
      workflowItems: 'trip items',
      createAction: 'Create New Trip',
      manageAction: 'Manage My Trip',
      myWorkflows: 'My Trips',
    },
  },
  nursing: {
    displayName: 'Nursing Care',
    tagline: 'Intelligent care coordination with secure delegation',
    backgroundImage: '/images/nura-nursing.jpg',
    terminology: {
      workflow: 'work schedule',
      workflows: 'work schedules',
      workflowItem: 'task',
      workflowItems: 'tasks',
      createAction: 'Create Work Schedule',
      manageAction: 'Manage My Schedule',
      myWorkflows: 'My Schedules',
    },
  },
};

const currentDomain: AppDomain = (import.meta.env.VITE_DOMAIN as AppDomain) || 'travel';

export const config = {
  // Domain hint for policy selection
  domain: currentDomain,
  
  // Domain-specific configuration
  ...domainConfigs[currentDomain],
  
  // API URLs (can be overridden by env vars)
  apiUrls: {
    domainServices:
      import.meta.env.VITE_DOMAIN_SERVICES_API_URL ||
      'https://flowpilot-domain-services-api-737191827545.europe-west1.run.app',
    delegation:
      import.meta.env.VITE_DELEGATION_API_URL ||
      'https://flowpilot-delegation-api-737191827545.europe-west1.run.app',
    aiAgent:
      import.meta.env.VITE_AI_AGENT_API_URL ||
      'https://flowpilot-ai-agent-api-737191827545.europe-west1.run.app',
  },
} as const;

// Helper function to capitalize first letter
export function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// Helper to get terminology with capitalization
export const terminology = {
  workflow: config.terminology.workflow,
  workflows: config.terminology.workflows,
  workflowItem: config.terminology.workflowItem,
  workflowItems: config.terminology.workflowItems,
  Workflow: capitalize(config.terminology.workflow),
  Workflows: capitalize(config.terminology.workflows),
  WorkflowItem: capitalize(config.terminology.workflowItem),
  WorkflowItems: capitalize(config.terminology.workflowItems),
} as const;
