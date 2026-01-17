import { useEffect } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { WorkflowItemCard } from '../common/WorkflowItemCard';
import { ColdStartNotice } from '../common/ColdStartNotice';

export function MyTripPanel() {
  const {
    workflows,
    selectedWorkflowId,
    workflowItems,
    workflowTemplates,
    selectedWorkflowTemplateId,
    workflowStartDate,
    selectedPersona,
    personas,
    principalSub,
    loading,
    errorMessage,
    setSelectedWorkflowId,
    setSelectedWorkflowTemplateId,
    setWorkflowStartDate,
    loadWorkflowTemplates,
    loadWorkflows,
    selectWorkflow,
    createWorkflow,
  } = useAppState();

  // Load templates and workflows on mount
  useEffect(() => {
    if (workflowTemplates.length === 0) {
      loadWorkflowTemplates();
    }
    if (workflows.length === 0) {
      loadWorkflows();
    }
  }, []);

  const handleWorkflowChange = async (workflowId: string) => {
    if (workflowId) {
      await selectWorkflow(workflowId);
    } else {
      setSelectedWorkflowId(null);
    }
  };

  const handleCreateWorkflow = async () => {
    if (!selectedWorkflowTemplateId || !principalSub) return;
    
    // Always use selected persona, or first one if multiple exist, or single one
    const persona = selectedPersona || (personas.length > 0 ? personas[0] : undefined);
    const startDateString = workflowStartDate.toISOString().split('T')[0];
    
    await createWorkflow({
      template_id: selectedWorkflowTemplateId,
      principal_sub: principalSub,
      start_date: startDateString,
      persona,
    });
  };

  const selectedWorkflow = workflows.find((w) => w.workflow_id === selectedWorkflowId);
  // Persona is always available if we have personas (first one is auto-selected)
  const personaRequired = personas.length === 0;

  return (
    <div className="space-y-6">
      {/* Cold Start Notice */}
      <ColdStartNotice
        isLoading={loading}
        delayThresholdMs={3000}
        message="Services are waking up from hibernation. This may take 10-30 seconds on first use. Please wait..."
      />

      {/* Error Message */}
      {errorMessage && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {errorMessage}
        </div>
      )}

      {/* Create New Trip or Select Existing Trip */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <h3 className="text-lg font-medium text-nura-dark mb-4 flex items-center gap-2">
          <span>✈️</span>
          My trip
        </h3>

        {personaRequired && (
          <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
            <p className="text-sm text-orange-700">
              ⚠️ Please select a persona first
            </p>
          </div>
        )}

        <div className="space-y-4 mb-6">
          {/* Option 1: Create New Trip */}
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3">Create a new trip</h4>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Trip template
                </label>
                <select
                  value={selectedWorkflowTemplateId || ''}
                  onChange={(e) => setSelectedWorkflowTemplateId(e.target.value || null)}
                  disabled={personaRequired || loading}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50 text-sm"
                >
                  <option value="">Choose a trip template...</option>
                  {workflowTemplates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Start date
                </label>
                <input
                  type="date"
                  value={workflowStartDate.toISOString().split('T')[0]}
                  onChange={(e) => setWorkflowStartDate(new Date(e.target.value))}
                  disabled={personaRequired || loading}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50 text-sm"
                />
              </div>

              <button
                onClick={handleCreateWorkflow}
                disabled={
                  !selectedWorkflowTemplateId ||
                  personaRequired ||
                  loading
                }
                className="w-full px-4 py-2 bg-nura-orange text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {loading ? 'Creating...' : 'Create trip itinerary'}
              </button>
            </div>
          </div>

          {/* Option 2: Select Existing Trip */}
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-3">Select an existing trip</h4>
            <div>
              {workflows.length === 0 ? (
                <p className="text-sm text-gray-500 py-2">
                  No trips available. Create a trip from a template above.
                </p>
              ) : (
                <select
                  value={selectedWorkflowId || ''}
                  onChange={(e) => handleWorkflowChange(e.target.value)}
                  disabled={personaRequired || loading}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50 text-sm"
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
          </div>
        </div>

        {/* Itinerary Section - Only show when a trip is selected */}
        {selectedWorkflow && (
          <div className="pt-6 border-t">
            <div className="flex items-center gap-2 text-sm mb-4">
              <span className="text-gray-500">Trip ID</span>
              <code className="font-mono text-gray-900 bg-gray-50 px-2 py-1 rounded">
                {selectedWorkflow.workflow_id}
              </code>
              {selectedWorkflow.departure_date && (
                <>
                  <span className="text-gray-400">|</span>
                  <span className="text-gray-500">📅</span>
                  <span className="text-gray-900">{selectedWorkflow.departure_date}</span>
                </>
              )}
            </div>

            {/* Workflow Items List */}
            {workflowItems.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-nura-dark mb-3">Itinerary</h4>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {workflowItems.map((item) => {
                    const itemId = item.item_id || item.workflow_item_id || item.id;
                    return <WorkflowItemCard key={itemId} item={item} />;
                  })}
                </div>
              </div>
            )}

            {selectedWorkflowId && workflowItems.length === 0 && !loading && (
              <p className="text-sm text-gray-500 italic">
                No items in this trip yet.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
