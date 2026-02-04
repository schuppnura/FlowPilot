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
  DelegationResponse,
} from '../types/models';

interface SelectedPersona {
  title: string;
  circle: string;
}

interface AppState {
  // User info
  principalSub: string | null;
  username: string | null;
  personas: string[];
  personasDetailed: Array<{title: string; circle: string}>;
  selectedPersona: SelectedPersona | null;

  // Workflows
  workflows: Workflow[];
  selectedWorkflowId: string | null;
  workflowItems: WorkflowItem[];
  workflowTemplates: WorkflowTemplate[];
  selectedWorkflowTemplateId: string | null;
  workflowStartDate: Date;

  // Delegations
  delegations: DelegationResponse[];
  travelAgents: TravelAgentUser[];
  selectedDelegateId: string | null;
  delegationExpiresInDays: number;

  // Invitations
  invitees: TravelAgentUser[];
  selectedInviteeId: string | null;
  invitationExpiresInDays: number;

  // All users (for sharing modal)
  allUsers: TravelAgentUser[];

  // Agent runs
  lastAgentRun: AgentRunResponse | null;

  // UI state
  statusMessage: string;
  errorMessage: string;
  loading: boolean;
}

interface AppStateContextType extends AppState {
  // Actions
  setSelectedPersona: (persona: SelectedPersona | null) => void;
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
  reloadPersonas: () => Promise<void>;
  loadWorkflowTemplates: () => Promise<void>;
  loadWorkflows: () => Promise<void>;
  selectWorkflow: (workflowId: string) => Promise<void>;
  createWorkflow: (request: CreateWorkflowRequest) => Promise<void>;
  loadTravelAgents: () => Promise<void>;
  loadDelegations: () => Promise<void>;
  revokeDelegation: (delegationId: string) => Promise<void>;
  createDelegation: (request: CreateDelegationRequest) => Promise<void>;
  loadInvitees: (persona?: string) => Promise<void>;
  createInvitation: (request: CreateDelegationRequest) => Promise<void>;
  loadAllUsers: () => Promise<void>;
  runAgent: (workflowId: string, dryRun: boolean) => Promise<void>;
}

const AppStateContext = createContext<AppStateContextType | undefined>(undefined);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const { user, getToken, openSignInModal } = useAuth();
  const [state, setState] = useState<AppState>({
    principalSub: null,
    username: null,
    personas: [],
    personasDetailed: [],
    selectedPersona: null,
    workflows: [],
    selectedWorkflowId: null,
    workflowItems: [],
    workflowTemplates: [],
    selectedWorkflowTemplateId: null,
    workflowStartDate: new Date(),
    delegations: [],
    travelAgents: [],
    selectedDelegateId: null,
    delegationExpiresInDays: 7,
    invitees: [],
    selectedInviteeId: null,
    invitationExpiresInDays: 30,
    allUsers: [],
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

  const domainClientRef = useRef(new DomainServicesClient(getAccessTokenForAPI, openSignInModal));
  const delegationClientRef = useRef(new DelegationClient(getAccessTokenForAPI, openSignInModal));
  const userProfileClientRef = useRef(new UserProfileClient(getAccessTokenForAPI, openSignInModal));
  const agentClientRef = useRef(new AIAgentClient(getAccessTokenForAPI, openSignInModal));

  // Recreate clients when getAccessTokenForAPI or openSignInModal changes
  useEffect(() => {
    domainClientRef.current = new DomainServicesClient(getAccessTokenForAPI, openSignInModal);
    delegationClientRef.current = new DelegationClient(getAccessTokenForAPI, openSignInModal);
    userProfileClientRef.current = new UserProfileClient(getAccessTokenForAPI, openSignInModal);
    agentClientRef.current = new AIAgentClient(getAccessTokenForAPI, openSignInModal);
  }, [getAccessTokenForAPI, openSignInModal]);

  // Reloadable personas function
  const reloadPersonas = useCallback(async () => {
    if (!user) return;
    console.log('AppStateContext: Reloading personas from API...');
    try {
      // Fetch detailed personas (with title, circle, etc.)
      const personasDetailed = await userProfileClientRef.current.getPersonasDetailed();
      console.log('AppStateContext: Loaded detailed personas from API:', personasDetailed);
      
      // Also keep titles array for backward compatibility
      const personas = Array.from(new Set(personasDetailed.map(p => p.title)));
      
      setState((prev) => {
        const newState = { 
          ...prev, 
          personas,
          personasDetailed: personasDetailed.map(p => ({ title: p.title, circle: p.circle }))
        };
        
        // Preserve user's manual selection if it's still valid
        if (prev.selectedPersona) {
          const stillValid = personasDetailed.some(
            p => p.title === prev.selectedPersona!.title && p.circle === prev.selectedPersona!.circle
          );
          if (stillValid) {
            console.log('AppStateContext: Keeping current persona selection:', prev.selectedPersona);
            return newState;
          }
        }
        
        // Only auto-select if there's no valid selection:
        // - If only one persona, select it
        // - If multiple personas, prefer traveler/business-traveler over delegation personas
        if (personasDetailed.length === 1) {
          newState.selectedPersona = {
            title: personasDetailed[0].title,
            circle: personasDetailed[0].circle,
          };
          console.log('AppStateContext: Auto-selected persona (single):', newState.selectedPersona);
        } else if (personasDetailed.length > 1 && !prev.selectedPersona) {
          // Prefer traveler personas over delegation personas for workflow operations
          const travelerPersonas = personasDetailed.filter(
            p => p.title === 'traveler' || p.title === 'business-traveler'
          );
          if (travelerPersonas.length > 0) {
            newState.selectedPersona = {
              title: travelerPersonas[0].title,
              circle: travelerPersonas[0].circle,
            };
            console.log('AppStateContext: Auto-selected traveler persona:', newState.selectedPersona);
          } else {
            newState.selectedPersona = {
              title: personasDetailed[0].title,
              circle: personasDetailed[0].circle,
            };
            console.log('AppStateContext: Auto-selected first persona:', newState.selectedPersona);
          }
        } else if (personasDetailed.length === 0) {
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
  }, [user]);

  // Load personas from persona-api when user changes
  useEffect(() => {
    if (user) {
      reloadPersonas();
    } else {
      console.log('AppStateContext: No user, clearing personas');
      setState((prev) => ({ ...prev, personas: [], selectedPersona: null }));
    }
  }, [user, reloadPersonas]);

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

  // Refetch workflow items when selected persona changes
  useEffect(() => {
    const currentState = stateRef.current;
    // If we have a selected workflow and persona changed, refetch items
    if (currentState.selectedWorkflowId && currentState.selectedPersona) {
      console.log('AppStateContext: Persona changed, refetching workflow items for:', currentState.selectedWorkflowId);
      selectWorkflow(currentState.selectedWorkflowId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.selectedPersona]);

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
      // Use selected persona or fallback to first detailed persona
      let personaTitle: string | undefined;
      let personaCircle: string | undefined;
      
      if (currentState.selectedPersona) {
        personaTitle = currentState.selectedPersona.title;
        personaCircle = currentState.selectedPersona.circle;
      } else if (currentState.personasDetailed.length > 0) {
        // Fallback to first detailed persona
        personaTitle = currentState.personasDetailed[0].title;
        personaCircle = currentState.personasDetailed[0].circle;
      }
      
      if (!personaTitle || !personaCircle) {
        throw new Error('No persona available. Please ensure your account has a persona assigned.');
      }
      console.log('selectWorkflow: Using persona:', personaTitle, '/', personaCircle, '(full:', currentState.selectedPersona, ')');
      const items = await domainClientRef.current.fetchWorkflowItems(workflowId, personaTitle, personaCircle);
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
      // Use selected persona or fallback to first detailed persona
      let personaTitle: string | undefined;
      let personaCircle: string | undefined;
      
      if (currentState.selectedPersona) {
        personaTitle = currentState.selectedPersona.title;
        personaCircle = currentState.selectedPersona.circle;
      } else if (currentState.personasDetailed.length > 0) {
        // Fallback to first detailed persona
        personaTitle = currentState.personasDetailed[0].title;
        personaCircle = currentState.personasDetailed[0].circle;
      }
      
      if (!personaTitle || !personaCircle) {
        throw new Error('No persona available. Please ensure your account has a persona assigned.');
      }
      const items = await domainClientRef.current.fetchWorkflowItems(workflowId, personaTitle, personaCircle);
      setState((prev) => ({
        ...prev,
        workflows,
        selectedWorkflowId: workflowId,
        workflowItems: items,
        loading: false,
      }));
    } catch (error: any) {
      console.error('createWorkflow error:', error);
      
      // Parse error message for user-friendly display
      let errorMessage = `Create workflow failed: ${error.message}`;
      
      // Check for 403 errors (access denied)
      if (error.statusCode === 403) {
        try {
          const bodyMatch = error.message.match(/\{.*\}/);
          if (bodyMatch) {
            const errorBody = JSON.parse(bodyMatch[0]);
            const detail = errorBody.detail;
            
            if (detail && typeof detail === 'object') {
              const reasonCodes = detail.reason_codes || [];
              
              // Map reason codes to user-friendly messages
              if (reasonCodes.includes('auto_book.persona_invalid')) {
                errorMessage = '❌ Cannot create itinerary: Your account persona is not currently active. Please check your account status or contact support.';
              } else if (reasonCodes.length > 0) {
                errorMessage = `❌ Access Denied: ${reasonCodes.join(', ')}`;
              } else {
                errorMessage = '❌ Access Denied: You do not have permission to perform this action.';
              }
            }
          }
        } catch (parseError) {
          console.error('Failed to parse error body:', parseError);
        }
      }
      
      setState((prev) => ({
        ...prev,
        errorMessage,
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
      
      // Parse error message for user-friendly display
      let userMessage = error.message || 'Unknown error';
      
      // Check for 403 errors (access denied)
      if (error.statusCode === 403) {
        try {
          const bodyMatch = error.message.match(/\{.*\}/);
          if (bodyMatch) {
            const errorBody = JSON.parse(bodyMatch[0]);
            const detail = errorBody.detail;
            
            if (detail && typeof detail === 'object') {
              const reasonCodes = detail.reason_codes || [];
              
              if (reasonCodes.includes('read.no_read_delegation') || reasonCodes.includes('workflow_access_denied')) {
                userMessage = '❌ Access Denied: You do not have permission to delegate this itinerary. Only the owner can create delegations.';
              } else if (reasonCodes.length > 0) {
                userMessage = `❌ Access Denied: ${reasonCodes.join(', ')}`;
              } else {
                userMessage = '❌ Access Denied: You do not have permission to perform this action.';
              }
            }
          }
        } catch (parseError) {
          console.error('Failed to parse error body:', parseError);
        }
      }
      // Check for duplicate delegation
      else if (userMessage.includes('already exists')) {
        userMessage = `Delegation to ${delegateEmail} already exists for this workflow. Please revoke the existing delegation first if you want to create a new one with different settings.`;
      }
      
      setState((prev) => ({
        ...prev,
        errorMessage: userMessage,
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
      
      // Parse error message for user-friendly display
      let userMessage = error.message || 'Unknown error';
      
      // Check for 403 errors (access denied)
      if (error.statusCode === 403) {
        try {
          const bodyMatch = error.message.match(/\{.*\}/);
          if (bodyMatch) {
            const errorBody = JSON.parse(bodyMatch[0]);
            const detail = errorBody.detail;
            
            if (detail && typeof detail === 'object') {
              const reasonCodes = detail.reason_codes || [];
              
              if (reasonCodes.includes('read.no_read_delegation') || reasonCodes.includes('workflow_access_denied')) {
                userMessage = '❌ Access Denied: You do not have permission to share this itinerary. Only the owner can send invitations.';
              } else if (reasonCodes.length > 0) {
                userMessage = `❌ Access Denied: ${reasonCodes.join(', ')}`;
              } else {
                userMessage = '❌ Access Denied: You do not have permission to perform this action.';
              }
            }
          }
        } catch (parseError) {
          console.error('Failed to parse error body:', parseError);
        }
      }
      // Check for duplicate invitation
      else if (userMessage.includes('already exists')) {
        userMessage = `Invitation to ${inviteeEmail} already exists for this workflow. The existing invitation is still active.`;
      }
      
      setState((prev) => ({
        ...prev,
        errorMessage: userMessage,
        loading: false,
        statusMessage: '',
      }));
    }
  }, [user]);

  const loadDelegations = useCallback(async () => {
    if (!user) {
      console.log('loadDelegations: No user, skipping');
      return;
    }
    
    console.log('loadDelegations: Loading delegations for user:', user.uid);
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const delegations = await delegationClientRef.current.fetchDelegations(user.uid);
      console.log('loadDelegations: Loaded', delegations.length, 'delegations');
      setState((prev) => ({ ...prev, delegations, loading: false }));
    } catch (error: any) {
      console.error('Error loading delegations:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Load delegations failed: ${error.message}`,
        loading: false,
        delegations: [],
      }));
    }
  }, [user]);

  const revokeDelegation = useCallback(async (delegationId: string) => {
    console.log('AppStateContext.revokeDelegation: Called with delegationId:', delegationId);
    if (!user) {
      console.error('AppStateContext.revokeDelegation: No user, aborting');
      return;
    }
    setState((prev) => ({ ...prev, loading: true, errorMessage: '', statusMessage: '' }));
    try {
      // Find the delegation object by ID
      console.log('AppStateContext.revokeDelegation: Searching for delegation in', stateRef.current.delegations.length, 'delegations');
      const delegation = stateRef.current.delegations.find(d => d.delegation_id === delegationId);
      if (!delegation) {
        console.error('AppStateContext.revokeDelegation: Delegation not found in state!');
        throw new Error('Delegation not found');
      }
      console.log('AppStateContext.revokeDelegation: Found delegation:', delegation);
      
      console.log('AppStateContext.revokeDelegation: Calling delegation client...');
      await delegationClientRef.current.revokeDelegation(delegation);
      console.log('AppStateContext.revokeDelegation: Client call succeeded, reloading delegations...');
      // Reload delegations to reflect the change
      await loadDelegations();
      console.log('AppStateContext.revokeDelegation: Reload complete, setting success message');
      setState((prev) => ({
        ...prev,
        statusMessage: 'Successfully revoked delegation',
        loading: false,
      }));
    } catch (error: any) {
      console.error('AppStateContext.revokeDelegation: Error occurred:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Revoke delegation failed: ${error.message}`,
        loading: false,
      }));
    }
  }, [user, loadDelegations]);

  const loadAllUsers = useCallback(async () => {
    if (!user) {
      console.log('loadAllUsers: No user, skipping');
      return;
    }
    
    console.log('loadAllUsers: Loading all users in the system...');
    setState((prev) => ({ ...prev, loading: true, errorMessage: '' }));
    try {
      const allUsers = await userProfileClientRef.current.listAllUsers();
      
      // Filter out self
      const filteredUsers = allUsers.filter((u) => u.id !== user.uid);
      console.log('loadAllUsers: Loaded', filteredUsers.length, 'users (excluding self)');
      setState((prev) => ({ ...prev, allUsers: filteredUsers, loading: false }));
    } catch (error: any) {
      console.error('Error loading all users:', error);
      setState((prev) => ({
        ...prev,
        errorMessage: `Load users failed: ${error.message}`,
        loading: false,
        allUsers: [],
      }));
    }
  }, [user]);

  const runAgent = useCallback(async (workflowId: string, dryRun: boolean) => {
    if (!user) return;
    setState((prev) => ({ ...prev, loading: true, errorMessage: '', statusMessage: '' }));
    try {
      const currentState = stateRef.current;
      // Use selected persona or fallback to first detailed persona
      let personaTitle: string | undefined;
      let personaCircle: string | undefined;
      
      if (currentState.selectedPersona) {
        personaTitle = currentState.selectedPersona.title;
        personaCircle = currentState.selectedPersona.circle;
      } else if (currentState.personasDetailed.length > 0) {
        // Fallback to first detailed persona
        personaTitle = currentState.personasDetailed[0].title;
        personaCircle = currentState.personasDetailed[0].circle;
      }
      
      console.log('runAgent: Using persona:', personaTitle, '/', personaCircle, '(selectedPersona:', currentState.selectedPersona, ')');
      if (!personaTitle || !personaCircle) {
        throw new Error('No persona available. Please ensure your account has a persona assigned.');
      }
      const result = await agentClientRef.current.runAgent({
        workflow_id: workflowId,
        principal_sub: user.uid,
        dry_run: dryRun,
        persona_title: personaTitle,
        persona_circle: personaCircle,
      });
      
      // Check for workflow-level authorization error
      if (result.error) {
        const reasonCodes = result.error.reason_codes || [];
        let errorMessage = result.error.message || 'Workflow execution not authorized';
        
        // Map reason codes to user-friendly messages with actionable guidance
        if (reasonCodes.some(code => code.includes('no_consent'))) {
          errorMessage = '🚫 Booking Not Allowed\n\n' +
            'You have not given consent for autonomous booking.\n\n' +
            'To enable booking:\n' +
            '1. Go to "My Account" (top right)\n' +
            '2. Click "Edit Persona"\n' +
            '3. Enable "Auto-booking Consent"\n' +
            '4. Save your changes and try again';
        } else if (reasonCodes.some(code => code.includes('cost_limit_exceeded'))) {
          errorMessage = '💰 Cost Limit Exceeded\n\n' +
            'This workflow\'s total cost exceeds your maximum auto-booking price limit.\n\n' +
            'To proceed:\n' +
            '• Increase your "Max Price" setting in your persona preferences, or\n' +
            '• Remove expensive items from the workflow';
        } else if (reasonCodes.some(code => code.includes('airline_risk_too_high'))) {
          errorMessage = '⚠️ Risk Score Too High\n\n' +
            'One or more flight items have an airline risk score that exceeds your configured tolerance.\n\n' +
            'To proceed:\n' +
            '• Increase your "Max Risk Level" in persona settings, or\n' +
            '• Choose flights with lower risk ratings';
        } else if (reasonCodes.some(code => code.includes('insufficient_advance_notice'))) {
          errorMessage = '📅 Insufficient Advance Notice\n\n' +
            'The departure date is too soon based on your minimum lead time requirement.\n\n' +
            'To proceed:\n' +
            '• Reduce your "Min Lead Time (days)" in persona settings, or\n' +
            '• Choose a later departure date';
        } else if (reasonCodes.some(code => code.includes('persona_invalid'))) {
          errorMessage = '👤 Persona Not Valid\n\n' +
            'Your persona is not currently active or is outside its validity period.\n\n' +
            'To proceed:\n' +
            '1. Go to "My Account"\n' +
            '2. Check your persona status and validity dates\n' +
            '3. Activate your persona or adjust the validity period';
        } else if (reasonCodes.some(code => code.includes('persona_mismatch'))) {
          errorMessage = '👤 Persona Type Mismatch\n\n' +
            'Your current persona type is not authorized to perform this action.\n\n' +
            'You may need to switch to a different persona or request delegation.';
        } else if (reasonCodes.some(code => code.includes('unauthorized_principal'))) {
          errorMessage = '🔒 Access Denied\n\n' +
            'You do not have permission to execute this workflow.\n\n' +
            'The workflow owner needs to delegate execution rights to you.';
        } else if (reasonCodes.length > 0) {
          // Check if user is the workflow owner to provide context-appropriate message
          const currentState = stateRef.current;
          const workflow = currentState.workflows.find(w => w.workflow_id === workflowId);
          const isOwner = workflow && workflow.owner_sub === user.uid;
          
          if (isOwner) {
            errorMessage = `❌ Authorization Failed\n\nReason: ${reasonCodes.join(', ')}\n\n` +
              'This workflow cannot be executed due to policy restrictions. ' +
              'Please review your persona settings and preferences.';
          } else {
            errorMessage = `❌ Authorization Failed\n\nReason: ${reasonCodes.join(', ')}\n\n` +
              'This workflow cannot be executed due to policy restrictions. ' +
              'You may need delegation from the workflow owner or to adjust your persona settings.';
          }
        }
        
        setState((prev) => ({
          ...prev,
          errorMessage,
          loading: false,
          statusMessage: '',
        }));
        return;
      }
      
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
        const items = await domainClientRef.current.fetchWorkflowItems(workflowId, personaTitle);
        setState((prev) => ({
          ...prev,
          workflowItems: items,
          statusMessage: prev.statusMessage, // Preserve statusMessage
        }));
      }
    } catch (error: any) {
      console.error('runAgent error:', error);
      
      // Parse 403 errors to extract reason codes and show user-friendly message
      let errorMessage = `Agent run failed: ${error.message}`;
      
      if (error.statusCode === 403) {
        try {
          // Try to parse the error body
          const bodyMatch = error.message.match(/\{.*\}/);
          if (bodyMatch) {
            const errorBody = JSON.parse(bodyMatch[0]);
            const detail = errorBody.detail;
            
            if (detail && typeof detail === 'object') {
              const reasonCodes = detail.reason_codes || [];
              
              // Map reason codes to user-friendly messages
              if (reasonCodes.includes('read.no_read_delegation')) {
                errorMessage = '❌ Access Denied: You do not have permission to book this itinerary. The owner has not delegated booking rights to you.';
              } else if (reasonCodes.includes('workflow_access_denied')) {
                errorMessage = '❌ Access Denied: You do not have permission to access this itinerary.';
              } else if (reasonCodes.length > 0) {
                errorMessage = `❌ Access Denied: ${reasonCodes.join(', ')}`;
              } else {
                errorMessage = '❌ Access Denied: You do not have permission to perform this action.';
              }
            }
          }
        } catch (parseError) {
          // If parsing fails, keep the original error message
          console.error('Failed to parse error body:', parseError);
        }
      }
      
      setState((prev) => ({
        ...prev,
        errorMessage,
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
    reloadPersonas,
    loadWorkflowTemplates,
    loadWorkflows,
    selectWorkflow,
    createWorkflow,
    loadTravelAgents,
    loadDelegations,
    revokeDelegation,
    createDelegation,
    loadInvitees,
    createInvitation,
    loadAllUsers,
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
