import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from './AuthContext';
import { DomainServicesClient } from '../services/api/domainServices';
import { DelegationClient } from '../services/api/delegation';
import { UserProfileClient } from '../services/api/userProfile';
import { AIAgentClient } from '../services/api/aiAgent';
import type {
  WorkflowTemplate,
  Workflow,
  WorkflowItem,
  TravelAgentUser,
  AgentRunResponse,
  CreateWorkflowRequest,
  CreateDelegationRequest,
} from '../types/models';

interface AppState {
  // User info
  principalSub: string | null;
  username: string | null;
  personas: string[];
  selectedPersona: string | null;

  // Workflows
  workflows: Workflow[];
  selectedWorkflowId: string | null;
  workflowItems: WorkflowItem[];
  workflowTemplates: WorkflowTemplate[];
  selectedWorkflowTemplateId: string | null;
  workflowStartDate: Date;

  // Delegations
  travelAgents: TravelAgentUser[];
  selectedDelegateId: string | null;
  delegationExpiresInDays: number;

  // Invitations
  invitees: TravelAgentUser[];
  selectedInviteeId: string | null;
  invitationExpiresInDays: number;

  // Agent runs
  lastAgentRun: AgentRunResponse | null;

  // UI state
  statusMessage: string;
  errorMessage: string;
  loading: boolean;
}

interface AppStateContextType extends AppState {
  // Actions
  setSelectedPersona: (persona: string | null) => void;
  setSelectedWorkflowId: (workflowId: string | null) => void;
  setSelectedWorkflowTemplateId: (templateId: string | null) => void;
  setWorkflowStartDate: (date: Date) => void;
  setSelectedDelegateId: (delegateId: string | null) => void;
  setDelegationExpiresInDays: (days: number) => void;
  setSelectedInviteeId: (inviteeId: string | null) => void;
  setInvitationExpiresInDays: (days: number) => void;
  clearError: () => void;
  setError: (message: string) => void;
  setStatus: (message: string) => void;

  // API actions
  loadWorkflowTemplates: () => Promise<void>;
  loadWorkflows: () => Promise<void>;
  selectWorkflow: (workflowId: string) => Promise<void>;
  createWorkflow: (request: CreateWorkflowRequest) => Promise<void>;
  loadTravelAgents: () => Promise<void>;
  createDelegation: (request: CreateDelegationRequest) => Promise<void>;
  loadInvitees: (persona?: string) => Promise<void>;
  createInvitation: (request: CreateDelegationRequest) => Promise<void>;
  runAgent: (workflowId: string, dryRun: boolean) => Promise<void>;
}

const AppStateContext = createContext<AppStateContextType | undefined>(undefined);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const { user, getToken } = useAuth();
  const [state, setState] = useState<AppState>({
    principalSub: null,
    username: null,
    personas: [],
    selectedPersona: null,
    workflows: [],
    selectedWorkflowId: null,
    workflowItems: [],
    workflowTemplates: [],
    selectedWorkflowTemplateId: null,
    workflowStartDate: new Date(),
    travelAgents: [],
    selectedDelegateId: null,
    delegationExpiresInDays: 7,
    invitees: [],
    selectedInviteeId: null,
    invitationExpiresInDays: 30,
    lastAgentRun: null,
    statusMessage: '',
    errorMessage: '',
    loading: false,
  });

  // Use ref to access latest state in callbacks
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Initialize API clients
  // Use access token (pseudonymous, sub only) for API calls
  const getAccessTokenForAPI = useCallback(async () => {
    if (!user) return null;
    return await getToken();  // Returns FlowPilot access token
  }, [user, getToken]);

  const domainClientRef = useRef(new DomainServicesClient(getAccessTokenForAPI));
  const delegationClientRef = useRef(new DelegationClient(getAccessTokenForAPI));
  const userProfileClientRef = useRef(new UserProfileClient(getAccessTokenForAPI));
  const agentClientRef = useRef(new AIAgentClient(getAccessTokenForAPI));

  // Recreate clients when getAccessTokenForAPI changes
  useEffect(() => {
    domainClientRef.current = new DomainServicesClient(getAccessTokenForAPI);
    delegationClientRef.current = new DelegationClient(getAccessTokenForAPI);
    userProfileClientRef.current = new UserProfileClient(getAccessTokenForAPI);
    agentClientRef.current = new AIAgentClient(getAccessTokenForAPI);
  }, [getAccessTokenForAPI]);

  // Load personas from persona-api when user changes
  useEffect(() => {
    if (user) {
      console.log('AppStateContext: Loading personas from API...');
      const loadPersonas = async () => {
        try {
          const personas = await userProfileClientRef.current.listPersonas();
          console.log('AppStateContext: Loaded personas from API:', personas);
          setState((prev) => {
            const newState = { ...prev, personas };
            // Always auto-select a persona:
            // - If only one persona, select it
            // - If multiple personas, select the first one (unless a valid selection already exists)
            if (personas.length === 1) {
              newState.selectedPersona = personas[0];
              console.log('AppStateContext: Auto-selected persona (single):', personas[0]);
            } else if (personas.length > 1) {
              // If current selection is still valid, keep it; otherwise select the first one
              if (prev.selectedPersona && personas.includes(prev.selectedPersona)) {
                console.log('AppStateContext: Keeping current persona selection:', prev.selectedPersona);
              } else {
                newState.selectedPersona = personas[0];
                console.log('AppStateContext: Auto-selected first persona (multiple):', personas[0]);
              }
            } else {
              // No personas found
              newState.selectedPersona = null;
              console.log('AppStateContext: No personas found, cleared selection');
            }
            return newState;
          });
        } catch (error) {
          console.error('AppStateContext: Failed to load personas:', error);
          setState((prev) => ({ ...prev, personas: [], selectedPersona: null }));
        }
      };
      loadPersonas();
    } else {
      console.log('AppStateContext: No user, clearing personas');
      setState((prev) => ({ ...prev, personas: [], selectedPersona: null }));
    }
  }, [user]);

  // Update user info when auth changes
  useEffect(() => {
    if (user) {
      setState((prev) => ({
        ...prev,
        principalSub: user.uid,
        username: user.email?.split('@')[0] || null,
      }));
    } else {
      setState((prev) => ({
        ...prev,
        principalSub: null,
        username: null,
        workflows: [],
        workflowItems: [],
        workflowTemplates: [],
        travelAgents: [],
        invitees: [],
        selectedWorkflowId: null,
        selectedPersona: null,
      }));
    }
  }, [user]);

  // Actions
  const loadWorkflowTemplates = useCallback(async () => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      console.log('Loading workflow templates...');
      const templates = await domainClientRef.current.fetchTemplates();
      console.log('Templates loaded:', templates);
      setState((prev) => ({
        ...prev,
        workflowTemplates: templates,
        selectedWorkflowTemplateId: templates[0]?.template_id || null,
        loading: false,
      }));
    } catch (error: any) {
      console.error('Error loading templates:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Load templates failed: ${error.message}`,
        loading: false,
      }));
    }
  }, [user]);

  const loadWorkflows = useCallback(async () => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const workflows = await domainClientRef.current.fetchWorkflows();
      setState((prev) => ({ ...prev, workflows, loading: false }));
    } catch (error: any) {
      setState((prev) => ({
        ...prev,
        errorMessage: `Load workflows failed: ${error.message}`,
        loading: false,
      }));
    }
  }, [user]);

  const selectWorkflow = useCallback(async (workflowId: string) => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const currentState = stateRef.current;
      // Always use selected persona, or first one if multiple exist, or single one
      const persona = currentState.selectedPersona || 
                     (currentState.personas.length > 0 ? currentState.personas[0] : undefined);
      if (!persona) {
        throw new Error('No persona available. Please ensure your account has a persona assigned.');
      }
      console.log('selectWorkflow: Using persona:', persona);
      const items = await domainClientRef.current.fetchWorkflowItems(workflowId, persona);
      setState((prev) => ({
        ...prev,
        selectedWorkflowId: workflowId,
        workflowItems: items,
        loading: false,
      }));
    } catch (error: any) {
      setState((prev) => ({
        ...prev,
        errorMessage: `Load workflow items failed: ${error.message}`,
        loading: false,
      }));
    }
  }, [user]);

  const createWorkflow = useCallback(async (request: CreateWorkflowRequest) => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const workflowId = await domainClientRef.current.createWorkflow(request);
      // Reload workflows and select the new one
      const workflows = await domainClientRef.current.fetchWorkflows();
      const currentState = stateRef.current;
      // Always use selected persona, or first one if multiple exist, or single one
      const persona = currentState.selectedPersona || 
                     (currentState.personas.length > 0 ? currentState.personas[0] : undefined);
      const items = await domainClientRef.current.fetchWorkflowItems(workflowId, persona);
      setState((prev) => ({
        ...prev,
        workflows,
        selectedWorkflowId: workflowId,
        workflowItems: items,
        loading: false,
      }));
    } catch (error: any) {
      setState((prev) => ({
        ...prev,
        errorMessage: `Create workflow failed: ${error.message}`,
        loading: false,
      }));
    }
  }, [user]);

  const loadTravelAgents = useCallback(async () => {
    if (!user) {
      console.log('loadTravelAgents: No user, skipping');
      return;
    }
    // Don't reload if already loaded
    const currentState = stateRef.current;
    if (currentState.travelAgents.length > 0) {
      console.log('loadTravelAgents: Already loaded', currentState.travelAgents.length, 'agents');
      return;
    }
    
    console.log('loadTravelAgents: Loading users with delegation personas (travel-agent, office-manager, booking-assistant)...');
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      // Search for all delegation-capable personas
      const personas = ['travel-agent', 'office-manager', 'booking-assistant'];
      const allAgents = await Promise.all(
        personas.map(p => userProfileClientRef.current.listUsersByPersona(p))
      );
      
      // Flatten and deduplicate by user ID
      const agentsMap = new Map();
      allAgents.flat().forEach(agent => {
        if (!agentsMap.has(agent.id)) {
          agentsMap.set(agent.id, agent);
        }
      });
      const agents = Array.from(agentsMap.values());
      
      console.log('loadTravelAgents: Loaded', agents.length, 'unique agents:', agents);
      setState((prev) => ({ ...prev, travelAgents: agents, loading: false, statusMessage: prev.statusMessage })); // Preserve statusMessage
    } catch (error: any) {
      console.error('Error loading travel agents:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Load travel agents failed: ${error.message}`,
        loading: false,
        travelAgents: [],
      }));
    }
  }, [user]);

  const createDelegation = useCallback(async (request: CreateDelegationRequest) => {
    if (!user) return;
    // Get delegate email before clearing state
      const delegateEmail = stateRef.current.travelAgents.find((a) => a.id === request.delegate_id)?.email || 'travel agent';
    
    console.log('createDelegation: Starting, current statusMessage:', stateRef.current.statusMessage);
    setState((prev) => {
      console.log('createDelegation: Clearing statusMessage, prev statusMessage:', prev.statusMessage);
      return { ...prev, loading: true, errorMessage: '', statusMessage: '' };
    });
    try {
      await delegationClientRef.current.createDelegation(request);
      const successMessage = `Successfully delegated to ${delegateEmail}. Expires in ${request.expires_in_days} days.`;
      console.log('createDelegation: API call succeeded, setting statusMessage:', successMessage);
      
      // Set statusMessage FIRST, then update other state
      setState((prev) => {
        console.log('createDelegation: Setting statusMessage in state, prev statusMessage:', prev.statusMessage);
        return {
          ...prev,
          statusMessage: successMessage, // Set this FIRST
          selectedDelegateId: null,
          loading: false,
        };
      });
      
      // Verify it was set immediately
      console.log('createDelegation: Immediately after setState, statusMessage should be:', successMessage);
      setTimeout(() => {
        console.log('createDelegation: After 100ms, statusMessage is:', stateRef.current.statusMessage);
      }, 100);
    } catch (error: any) {
      console.error('createDelegation: Error occurred:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Create delegation failed: ${error.message}`,
        loading: false,
        statusMessage: '',
      }));
    }
  }, [user]);

  const loadInvitees = useCallback(async () => {
    if (!user) {
      console.log('loadInvitees: No user, skipping');
      return;
    }
    
    console.log('loadInvitees: Loading users with invitation personas (traveler, business-traveler)...');
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      // Search for all invitation-capable personas
      const personas = ['traveler', 'business-traveler'];
      const allInvitees = await Promise.all(
        personas.map(p => userProfileClientRef.current.listUsersByPersona(p))
      );
      
      // Flatten and deduplicate by user ID
      const inviteesMap = new Map();
      allInvitees.flat().forEach(invitee => {
        if (!inviteesMap.has(invitee.id)) {
          inviteesMap.set(invitee.id, invitee);
        }
      });
      const users = Array.from(inviteesMap.values());
      
      // Filter out self
      const invitees = users.filter((u) => u.id !== user.uid);
      console.log('loadInvitees: Loaded', invitees.length, 'unique invitees (excluding self):', invitees);
      setState((prev) => ({ ...prev, invitees, loading: false, statusMessage: prev.statusMessage })); // Preserve statusMessage
    } catch (error: any) {
      console.error('Error loading invitees:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Load invitees failed: ${error.message}`,
        loading: false,
        invitees: [],
      }));
    }
  }, [user]);

  const createInvitation = useCallback(async (request: CreateDelegationRequest) => {
    if (!user) return;
    // Get invitee email before clearing state
      const inviteeEmail = stateRef.current.invitees.find((u) => u.id === request.delegate_id)?.email || 'user';
    
    console.log('createInvitation: Starting, current statusMessage:', stateRef.current.statusMessage);
    setState((prev) => {
      console.log('createInvitation: Clearing statusMessage, prev statusMessage:', prev.statusMessage);
      return { ...prev, loading: true, errorMessage: '', statusMessage: '' };
    });
    try {
      await delegationClientRef.current.createDelegation(request);
      const successMessage = `Successfully invited ${inviteeEmail}. Expires in ${request.expires_in_days} days.`;
      console.log('createInvitation: API call succeeded, setting statusMessage:', successMessage);
      
      // Set statusMessage FIRST, then update other state
      setState((prev) => {
        console.log('createInvitation: Setting statusMessage in state, prev statusMessage:', prev.statusMessage);
        return {
          ...prev,
          statusMessage: successMessage, // Set this FIRST
          selectedInviteeId: null,
          loading: false,
        };
      });
      
      // Verify it was set immediately
      console.log('createInvitation: Immediately after setState, statusMessage should be:', successMessage);
      setTimeout(() => {
        console.log('createInvitation: After 100ms, statusMessage is:', stateRef.current.statusMessage);
      }, 100);
    } catch (error: any) {
      console.error('createInvitation: Error occurred:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Create invitation failed: ${error.message}`,
        loading: false,
        statusMessage: '',
      }));
    }
  }, [user]);

  const runAgent = useCallback(async (workflowId: string, dryRun: boolean) => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '', statusMessage: '' }));
    try {
      const currentState = stateRef.current;
      // Always use selected persona, or first one if multiple exist, or single one
      const persona = currentState.selectedPersona || 
                     (currentState.personas.length > 0 ? currentState.personas[0] : undefined);
      console.log('runAgent: Using persona:', persona, '(selectedPersona:', currentState.selectedPersona, ', personas:', currentState.personas, ')');
      if (!persona) {
        throw new Error('No persona available. Please ensure your account has a persona assigned.');
      }
      const result = await agentClientRef.current.runAgent({
        workflow_id: workflowId,
        principal_sub: user.uid,
        dry_run: dryRun,
        persona,
      });
      
      // Calculate counts
      const allowedCount = result.results.filter((r) => r.decision.toLowerCase() === 'allow').length;
      const deniedCount = result.results.filter((r) => r.decision.toLowerCase() === 'deny').length;
      const errorCount = result.results.filter((r) => r.status.toLowerCase() === 'error').length;
      
      const actionLabel = dryRun ? 'Dry run' : 'Booking';
      let statusMsg = `${actionLabel} complete. Allowed=${allowedCount}, Denied=${deniedCount}, Errors=${errorCount}.`;
      
      // Add details for denials/errors
      const denials = result.results.filter(
        (r) => r.decision.toLowerCase() === 'deny' || r.status.toLowerCase() === 'error'
      );
      if (denials.length > 0) {
        const detailLines = denials.map((r) => {
          let line = `[${r.kind}] ${r.workflow_item_id}: ${r.status.toUpperCase()} - ${r.decision.toUpperCase()}`;
          if (r.reason_codes && r.reason_codes.length > 0) {
            line += ` | Reason: ${r.reason_codes.join(', ')}`;
          }
          if (r.advice && r.advice.length > 0) {
            const messages = r.advice.map((a) => a.message).join('; ');
            line += ` | ${messages}`;
          }
          return line;
        });
        statusMsg += '\n\nDetails:\n' + detailLines.join('\n');
      }
      
      setState((prev) => ({
        ...prev,
        lastAgentRun: result,
        loading: false,
        statusMessage: statusMsg,
      }));
      
      // Reload workflow items to show updated status (only for actual booking, not dry run)
      if (!dryRun) {
        const items = await domainClientRef.current.fetchWorkflowItems(workflowId, persona);
        setState((prev) => ({
          ...prev,
          workflowItems: items,
          statusMessage: prev.statusMessage, // Preserve statusMessage
        }));
      }
    } catch (error: any) {
      setState((prev) => ({
        ...prev,
        errorMessage: `Agent run failed: ${error.message}`,
        loading: false,
        statusMessage: '',
      }));
    }
  }, [user]);

  const value: AppStateContextType = {
    ...state,
    setSelectedPersona: (persona) =>
      setState((prev) => ({ ...prev, selectedPersona: persona })),
    setSelectedWorkflowId: (workflowId) =>
      setState((prev) => ({ ...prev, selectedWorkflowId: workflowId })),
    setSelectedWorkflowTemplateId: (templateId) =>
      setState((prev) => ({ ...prev, selectedWorkflowTemplateId: templateId })),
    setWorkflowStartDate: (date) =>
      setState((prev) => ({ ...prev, workflowStartDate: date })),
    setSelectedDelegateId: (delegateId) =>
      setState((prev) => ({ ...prev, selectedDelegateId: delegateId })),
    setDelegationExpiresInDays: (days) =>
      setState((prev) => ({ ...prev, delegationExpiresInDays: days })),
    setSelectedInviteeId: (inviteeId) =>
      setState((prev) => ({ ...prev, selectedInviteeId: inviteeId })),
    setInvitationExpiresInDays: (days) =>
      setState((prev) => ({ ...prev, invitationExpiresInDays: days })),
    clearError: () => setState((prev) => ({ ...prev, errorMessage: '' })),
    setError: (message) => setState((prev) => ({ ...prev, errorMessage: message })),
    setStatus: (message) => setState((prev) => ({ ...prev, statusMessage: message })),
    loadWorkflowTemplates,
    loadWorkflows,
    selectWorkflow,
    createWorkflow,
    loadTravelAgents,
    createDelegation,
    loadInvitees,
    createInvitation,
    runAgent,
  };

  return (
    <AppStateContext.Provider value={value}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const context = useContext(AppStateContext);
  if (context === undefined) {
    throw new Error('useAppState must be used within an AppStateProvider');
  }
  return context;
}
