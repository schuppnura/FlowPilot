import { useEffect, useRef } from 'react';
import { useAppState } from '../../state/AppStateContext';

export function InvitePanel() {
  const {
    workflows,
    invitees,
    selectedInviteeId,
    invitationExpiresInDays,
    selectedWorkflowId,
    selectedPersona,
    personas,
    loading,
    errorMessage,
    statusMessage,
    loadWorkflows,
    selectWorkflow,
    setSelectedWorkflowId,
    setSelectedInviteeId,
    setInvitationExpiresInDays,
    loadInvitees,
    createInvitation,
    setStatus,
    principalSub,
  } = useAppState();
  
  // Use refs to track loading state and prevent infinite loops
  const hasLoadedInviteesRef = useRef(false);
  const lastLoadedPersonaRef = useRef<string | null>(null);

  // Load workflows on mount
  useEffect(() => {
    if (workflows.length === 0) {
      loadWorkflows();
    }
  }, []);

  // Load invitees when persona becomes available
  // Use refs to prevent infinite loops
  useEffect(() => {
    // Get persona to use
    const personaToUse = selectedPersona || (personas.length > 0 ? personas[0] : null);
    if (!personaToUse) {
      console.log('InvitePanel: No persona available yet (personas:', personas.length, 'personas, selectedPersona:', selectedPersona, ')');
      return;
    }
    
    // If we've already loaded for this persona AND we have invitees, we're done
    if (hasLoadedInviteesRef.current && lastLoadedPersonaRef.current === personaToUse && invitees.length > 0) {
      // We have invitees for this persona - only skip reload if we have a relevant status message
      if (statusMessage && statusMessage.trim().length > 0 && statusMessage.includes('invited')) {
        console.log('InvitePanel: Already loaded invitees, skipping reload to preserve invitation statusMessage:', statusMessage);
        return;
      }
      console.log('InvitePanel: Already loaded invitees for persona:', personaToUse, ', count:', invitees.length);
      return;
    }
    
    // If we've loaded before but persona changed or no invitees, reset
    if (hasLoadedInviteesRef.current && (lastLoadedPersonaRef.current !== personaToUse || invitees.length === 0)) {
      console.log('InvitePanel: Persona changed or no invitees, resetting (was:', lastLoadedPersonaRef.current, ', now:', personaToUse, ', invitees:', invitees.length, ')');
      hasLoadedInviteesRef.current = false;
      lastLoadedPersonaRef.current = null;
    }
    
    // Don't check loading state - if we're loading something else, that's OK
    // We need to load invitees regardless. The loadInvitees function itself handles the loading state.
    
    // If we have invitees and a status message from invitation, preserve it
    if (invitees.length > 0 && statusMessage && statusMessage.trim().length > 0 && statusMessage.includes('invited')) {
      console.log('InvitePanel: Have invitees and invitation statusMessage, skipping reload to preserve message:', statusMessage);
      return;
    }
    
    // Load invitees (searches for all invitation personas: traveler, business-traveler)
    console.log('InvitePanel: Loading invitees (currently have', invitees.length, 'invitees, loading:', loading, ')');
    hasLoadedInviteesRef.current = true;
    lastLoadedPersonaRef.current = personaToUse;
    loadInvitees().catch((err) => {
      console.error('InvitePanel: Failed to load invitees:', err);
      hasLoadedInviteesRef.current = false; // Reset on error so we can retry
      lastLoadedPersonaRef.current = null;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPersona, personas.length]); // Depend on personas.length to detect when personas are loaded (don't depend on invitees.length to avoid loops)

  // Debug: Log statusMessage changes
  useEffect(() => {
    console.log('InvitePanel: statusMessage changed to:', statusMessage, '(length:', statusMessage?.length || 0, ')');
    if (statusMessage && statusMessage.trim().length > 0) {
      console.log('InvitePanel: ✅ statusMessage is set and should be visible!');
    } else {
      console.log('InvitePanel: ❌ statusMessage is empty or whitespace');
    }
  }, [statusMessage]);

  // Clear status message when this panel mounts if it's from a different action (delegation)
  // This ensures invitees can be loaded even if there's a leftover statusMessage
  useEffect(() => {
    // Clear status message from delegation/delegate actions when switching to invite tab
    if (statusMessage && statusMessage.includes('delegated')) {
      console.log('InvitePanel: Clearing delegation statusMessage to allow invitee loading');
      setStatus('');
    }
  }, []); // Only run once on mount
  
  // Clear status message only when navigating away from this tab (component unmounts)
  useEffect(() => {
    return () => {
      // Clear status message when component unmounts (tab change)
      // But only clear if it's an invitation status message, not delegation
      if (statusMessage && !statusMessage.includes('delegated')) {
        setStatus('');
      }
      // Reset refs when unmounting
      hasLoadedInviteesRef.current = false;
      lastLoadedPersonaRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run cleanup on unmount

  // Always use selected persona, or first one if multiple exist, or single one
  const personaToUse = selectedPersona || (personas.length > 0 ? personas[0] : null);
  // Persona is always available if we have personas (first one is auto-selected)
  const personaRequired = personas.length === 0;

  const handleWorkflowChange = async (workflowId: string) => {
    if (workflowId) {
      await selectWorkflow(workflowId);
    } else {
      setSelectedWorkflowId(null);
    }
  };

  const handleCreateInvitation = async () => {
    if (!selectedInviteeId || !selectedWorkflowId || !principalSub) return;

    await createInvitation({
      principal_id: principalSub,
      delegate_id: selectedInviteeId,
      workflow_id: selectedWorkflowId,
      scope: ['read'],
      expires_in_days: invitationExpiresInDays,
    });
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      <h2 className="text-2xl font-medium text-nura-dark mb-6 flex items-center gap-3">
        <span className="text-2xl">✉️</span>
        Invite
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
          Select trip
        </label>
        {workflows.length === 0 ? (
          <p className="text-sm text-gray-500 py-2">
            No trips available. Create a trip in the "My trip" tab first.
          </p>
        ) : (
          <select
            value={selectedWorkflowId || ''}
            onChange={(e) => handleWorkflowChange(e.target.value)}
            disabled={personaRequired || loading}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
          >
            <option value="">Select a trip...</option>
            {workflows.map((workflow) => (
              <option key={workflow.workflow_id} value={workflow.workflow_id}>
                {workflow.workflow_id} - {workflow.departure_date || 'no date'} ({workflow.item_count} items)
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Invite user
          </label>
          <select
            value={selectedInviteeId || ''}
            onChange={(e) => setSelectedInviteeId(e.target.value || null)}
            disabled={personaRequired || loading || !selectedWorkflowId}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
          >
            <option value="">Invite a user...</option>
            {invitees.map((user) => (
              <option key={user.id} value={user.id}>
                {user.email || 'Unknown user'}
              </option>
            ))}
          </select>
          {invitees.length === 0 && personaToUse && !loading && (
            <p className="text-xs text-gray-500 mt-1">
              No users with {personaToUse} persona found (excluding yourself)
            </p>
          )}
          {loading && (
            <p className="text-xs text-gray-500 mt-1">
              Loading users...
            </p>
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
              value={invitationExpiresInDays}
              onChange={(e) => setInvitationExpiresInDays(parseInt(e.target.value))}
              disabled={personaRequired || loading}
              className="flex-1"
            />
            <span className="text-sm font-medium text-gray-700 w-20">
              {invitationExpiresInDays} days
            </span>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <p className="text-sm text-blue-700 italic">
            Invites users with the same persona to view my trip (read-only)
          </p>
        </div>

        <button
          onClick={handleCreateInvitation}
          disabled={
            !selectedInviteeId ||
            !selectedWorkflowId ||
            personaRequired ||
            loading
          }
          className="w-full px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Sending invitation...' : 'Invite to View'}
        </button>

      </div>
    </div>
  );
}
