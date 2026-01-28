import { useEffect } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { StatusBadge } from '../common/StatusBadge';
import { terminology, capitalize } from '../../config';

export function BookPanel() {
  const {
    workflows,
    selectedWorkflowId,
    personas,
    lastAgentRun,
    loading,
    errorMessage,
    loadWorkflows,
    selectWorkflow,
    setSelectedWorkflowId,
    runAgent,
    clearError,
    setStatus,
  } = useAppState();
  
  // Clear errors and status messages when unmounting (switching away from) this panel
  useEffect(() => {
    return () => {
      clearError();
      setStatus('');
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load workflows on mount
  useEffect(() => {
    if (workflows.length === 0) {
      loadWorkflows();
    }
  }, []);

  // Persona is always available if we have personas (first one is auto-selected)
  const personaRequired = personas.length === 0;
  const canRun = selectedWorkflowId && !personaRequired;

  const handleWorkflowChange = async (workflowId: string) => {
    if (workflowId) {
      await selectWorkflow(workflowId);
    } else {
      setSelectedWorkflowId(null);
    }
  };

  const handleDryRun = async () => {
    if (!selectedWorkflowId) return;
    await runAgent(selectedWorkflowId, true);
  };

  const handleBookTrip = async () => {
    if (!selectedWorkflowId) return;
    await runAgent(selectedWorkflowId, false);
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-medium text-nura-dark flex items-center gap-3">
          <span className="text-2xl">📊</span>
          Book my {terminology.workflow}
        </h2>

        <div className="flex gap-3">
          <button
            onClick={handleDryRun}
            disabled={!canRun || loading}
            className="px-6 py-2 border-2 border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <span>🛡️</span>
            Dry Run
          </button>
          <button
            onClick={handleBookTrip}
            disabled={!canRun || loading}
            className="px-6 py-2 bg-red-700 text-white font-medium rounded-lg hover:bg-red-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <span>📅</span>
            Book {capitalize(terminology.workflow)}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {errorMessage}
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

      {lastAgentRun && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">Run ID:</span>
            <code className="font-mono text-gray-900 bg-gray-50 px-2 py-1 rounded">
              {lastAgentRun.run_id}
            </code>
          </div>

          <div className="max-h-96 overflow-y-auto space-y-2">
            {lastAgentRun.results.map((result) => (
              <div
                key={result.workflow_item_id}
                className="bg-white border border-gray-200 rounded-lg p-3"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm text-gray-900">
                        {result.kind}
                      </span>
                    </div>
                    <div className="space-y-1">
                      <code className="text-xs font-mono text-gray-700 block">
                        {result.workflow_item_id}
                      </code>
                      {result.decision.toLowerCase() === 'deny' &&
                        result.reason_codes &&
                        result.reason_codes.length > 0 && (
                          <p className="text-xs text-gray-500">
                            {result.reason_codes.join(', ')}
                          </p>
                        )}
                    </div>
                  </div>
                  <StatusBadge
                    status={result.status}
                    decision={result.decision}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!lastAgentRun && canRun && (
        <p className="text-sm text-gray-500 text-center py-8">
          Click "Dry Run" or "Book {capitalize(terminology.workflow)}" to see authorization results
        </p>
      )}
    </div>
  );
}
