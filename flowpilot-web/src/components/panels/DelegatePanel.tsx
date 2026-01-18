import { useEffect, useRef } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { useAuth } from '../../state/AuthContext';
import { PanelHeader } from '../common/PanelHeader';
import { terminology } from '../../config';

export function DelegatePanel() {
  const { openSignInModal } = useAuth();
  const {
    workflows,
    travelAgents,
    selectedDelegateId,
    delegationExpiresInDays,
    selectedWorkflowId,
    personas,
    loading,
    errorMessage,
    statusMessage,
    loadWorkflows,
    selectWorkflow,
    setSelectedWorkflowId,
    setSelectedDelegateId,
    setDelegationExpiresInDays,
    loadTravelAgents,
    createDelegation,
    setStatus,
    principalSub,
  } = useAppState();
  
  // Use ref to track if we've already loaded travel agents
  const hasLoadedTravelAgentsRef = useRef(false);

  // Load workflows on mount
  useEffect(() => {
    if (workflows.length === 0) {
      loadWorkflows();
    }
  }, []);

  // Load travel agents when personas are available
  // Use refs to prevent infinite loops
  useEffect(() => {
    // Wait for personas to be loaded
    if (personas.length === 0) {
      console.log('DelegatePanel: No personas available yet');
      return;
    }
    
    // If we've already loaded travel agents, we're done
    if (hasLoadedTravelAgentsRef.current && travelAgents.length > 0) {
      // We have travel agents - only skip reload if we have a relevant status message
      if (statusMessage && statusMessage.trim().length > 0 && statusMessage.includes('delegated')) {
        console.log('DelegatePanel: Already loaded travel agents, skipping reload to preserve delegation statusMessage:', statusMessage);
        return;
      }
      console.log('DelegatePanel: Already loaded travel agents, count:', travelAgents.length);
      return;
    }
    
    // If we have travel agents and a status message from delegation, preserve it
    if (travelAgents.length > 0 && statusMessage && statusMessage.trim().length > 0 && statusMessage.includes('delegated')) {
      console.log('DelegatePanel: Have travel agents and delegation statusMessage, skipping reload to preserve message:', statusMessage);
      return;
    }
    
    // Load travel agents (searches for all delegation personas: travel-agent, office-manager, booking-assistant)
    console.log('DelegatePanel: Loading travel agents (currently have', travelAgents.length, 'travel agents, loading:', loading, ')');
    hasLoadedTravelAgentsRef.current = true;
    loadTravelAgents().catch((err) => {
      console.error('DelegatePanel: Failed to load travel agents:', err);
      hasLoadedTravelAgentsRef.current = false; // Reset on error so we can retry
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personas.length]); // Depend on personas.length to detect when personas are loaded

  // Debug: Log statusMessage changes
  useEffect(() => {
    console.log('DelegatePanel: statusMessage changed to:', statusMessage, '(length:', statusMessage?.length || 0, ')');
    if (statusMessage && statusMessage.trim().length > 0) {
      console.log('DelegatePanel: ✅ statusMessage is set and should be visible!');
    } else {
      console.log('DelegatePanel: ❌ statusMessage is empty or whitespace');
    }
  }, [statusMessage]);

  // Clear status message when this panel mounts if it's from a different action (invitation)
  // This ensures travel agents can be loaded even if there's a leftover statusMessage
  useEffect(() => {
    // Clear status message from invitation actions when switching to delegate tab
    if (statusMessage && statusMessage.includes('invited')) {
      console.log('DelegatePanel: Clearing invitation statusMessage to allow travel agent loading');
      setStatus('');
    }
  }, []); // Only run once on mount
  
  // Clear status message only when navigating away from this tab (component unmounts)
  useEffect(() => {
    return () => {
      // Clear status message when component unmounts (tab change)
      // But only clear if it's a delegation status message, not invitation
      if (statusMessage && !statusMessage.includes('invited')) {
        setStatus('');
      }
      // Reset ref when unmounting
      hasLoadedTravelAgentsRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run cleanup on unmount

  // Persona is always available if we have personas (first one is auto-selected)
  const personaRequired = personas.length === 0;

  const handleWorkflowChange = async (workflowId: string) => {
    if (workflowId) {
      await selectWorkflow(workflowId);
    } else {
      setSelectedWorkflowId(null);
    }
  };

  const handleCreateDelegation = async () => {
    if (!selectedDelegateId || !selectedWorkflowId || !principalSub) return;

    await createDelegation({
      principal_id: principalSub,
      delegate_id: selectedDelegateId,
      workflow_id: selectedWorkflowId,
      scope: ['execute'],
      expires_in_days: delegationExpiresInDays,
    });
  };

  return (
    <div className="space-y-6">
      {/* Panel Header */}
      <PanelHeader onSignInClick={openSignInModal} />
      
      <div className="bg-white rounded-lg shadow-sm p-6">
      <h2 className="text-2xl font-medium text-nura-dark mb-6 flex items-center gap-3">
        <span className="text-2xl">👥</span>
        Delegate
      </h2>

      {errorMessage && (
        <div className="mb-4 bg-red-50 border-2 border-red-300 text-red-700 px-4 py-3 rounded-lg shadow-sm">
          {errorMessage}
        </div>
      )}

      {statusMessage && statusMessage.trim().length > 0 && (
        <div className="mb-4 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 rounded-lg shadow-md relative z-10">
          <p className="font-semibold text-base">✓ {statusMessage}</p>
        </div>
      )}

      {personaRequired && (
        <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
          <p className="text-sm text-orange-700">
            ⚠️ Please select a persona first
          </p>
        </div>
      )}

      {/* Trip Selection */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Select {terminology.workflow}
        </label>
        {workflows.length === 0 ? (
          <p className="text-sm text-gray-500 py-2">
            No {terminology.workflows} available. Create a {terminology.workflow} in the "{terminology.Workflows}" tab first.
          </p>
        ) : (
          <select
            value={selectedWorkflowId || ''}
            onChange={(e) => handleWorkflowChange(e.target.value)}
            disabled={personaRequired || loading}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
          >
            <option value="">Select a {terminology.workflow}...</option>
            {workflows.map((workflow) => (
              <option key={workflow.workflow_id} value={workflow.workflow_id}>
                {workflow.workflow_id} - {workflow.departure_date || 'no date'} ({workflow.item_count} {terminology.workflowItems})
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Travel agent
          </label>
          <select
            value={selectedDelegateId || ''}
            onChange={(e) => setSelectedDelegateId(e.target.value || null)}
            disabled={personaRequired || loading || !selectedWorkflowId}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
          >
            <option value="">Choose a travel agent...</option>
            {travelAgents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.email || 'Unknown user'}
              </option>
            ))}
          </select>
          {!loading && travelAgents.length === 0 && (
            <div className="mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-700">
                No travel agents available. Users must have one of these personas: <strong>travel-agent</strong>, <strong>office-manager</strong>, or <strong>booking-assistant</strong>.
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Expiration (days)
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="1"
              max="365"
              value={delegationExpiresInDays}
              onChange={(e) => setDelegationExpiresInDays(parseInt(e.target.value))}
              disabled={personaRequired || loading}
              className="flex-1"
            />
            <span className="text-sm font-medium text-gray-700 w-20">
              {delegationExpiresInDays} days
            </span>
          </div>
        </div>

        <button
          onClick={handleCreateDelegation}
          disabled={
            !selectedDelegateId ||
            !selectedWorkflowId ||
            personaRequired ||
            loading
          }
          className="w-full px-6 py-3 bg-nura-orange text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Creating delegation...' : 'Delegate Trip'}
        </button>

      </div>
    </div>
    </div>
  );
}
