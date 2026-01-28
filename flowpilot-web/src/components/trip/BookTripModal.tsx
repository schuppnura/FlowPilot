import { useState } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { StatusBadge } from '../common/StatusBadge';
import { terminology, capitalize } from '../../config';

interface BookTripModalProps {
  workflowId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function BookTripModal({ workflowId, isOpen, onClose }: BookTripModalProps) {
  const { workflows, lastAgentRun, runAgent, loading, personas } = useAppState();
  const [isRunning, setIsRunning] = useState(false);

  if (!isOpen || !workflowId) return null;

  const workflow = workflows.find((w) => w.workflow_id === workflowId);
  const personaRequired = personas.length === 0;

  if (!workflow) return null;

  const handleDryRun = async () => {
    setIsRunning(true);
    try {
      await runAgent(workflowId, true);
    } finally {
      setIsRunning(false);
    }
  };

  const handleBookTrip = async () => {
    setIsRunning(true);
    try {
      await runAgent(workflowId, false);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">📊</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">Book {capitalize(terminology.workflow)}</h2>
              <code className="text-sm font-mono text-gray-500">
                {workflow.workflow_id}
              </code>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {personaRequired && (
            <div className="p-3 bg-orange-50 border border-orange-200 rounded-lg">
              <p className="text-sm text-orange-700">
                ⚠️ Please select a persona first
              </p>
            </div>
          )}

          {/* Explanatory Text */}
          <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
            <h3 className="font-semibold text-gray-900 mb-2">Booking Options</h3>
            <div className="space-y-3 text-sm">
              <div>
                <p className="font-medium text-gray-900 mb-1">🛡️ Dry Run (Preview)</p>
                <p className="text-gray-700">
                  Simulates the booking process without making actual changes. Use this to see which items 
                  would be approved or denied by the authorization policies before committing to a real booking.
                </p>
              </div>
              <div>
                <p className="font-medium text-gray-900 mb-1">📅 Book {capitalize(terminology.workflow)}</p>
                <p className="text-gray-700">
                  Executes the actual booking process. The AI agent will attempt to book all workflow items 
                  according to your authorization policies and preferences. Items that pass authorization will 
                  be marked as completed.
                </p>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleDryRun}
              disabled={personaRequired || isRunning || loading}
              className="flex-1 px-6 py-3 border-2 border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <span>🛡️</span>
              {isRunning ? 'Running...' : 'Dry Run'}
            </button>
            <button
              onClick={handleBookTrip}
              disabled={personaRequired || isRunning || loading}
              className="flex-1 px-6 py-3 bg-red-700 text-white font-medium rounded-lg hover:bg-red-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <span>📅</span>
              {isRunning ? 'Booking...' : `Book ${capitalize(terminology.workflow)}`}
            </button>
          </div>

          {/* Agent Run Results */}
          {lastAgentRun && lastAgentRun.workflow_id === workflowId && (
            <div className="pt-4 border-t">
              <div className="flex items-center gap-2 text-sm mb-4">
                <span className="text-gray-500">Run ID:</span>
                <code className="font-mono text-gray-900 bg-gray-50 px-2 py-1 rounded">
                  {lastAgentRun.run_id}
                </code>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    lastAgentRun.dry_run
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-green-100 text-green-700'
                  }`}
                >
                  {lastAgentRun.dry_run ? 'Dry Run' : 'Live Booking'}
                </span>
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

          {!lastAgentRun && (
            <p className="text-sm text-gray-500 text-center py-8">
              Click "Dry Run" or "Book {capitalize(terminology.workflow)}" to see authorization results
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
