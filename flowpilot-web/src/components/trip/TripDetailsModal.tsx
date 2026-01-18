import { useEffect } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { terminology, capitalize, config } from '../../config';

interface TripDetailsModalProps {
  workflowId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function TripDetailsModal({ workflowId, isOpen, onClose }: TripDetailsModalProps) {
  const { workflows, workflowItems, selectWorkflow, loading } = useAppState();

  useEffect(() => {
    if (isOpen && workflowId) {
      selectWorkflow(workflowId);
    }
  }, [isOpen, workflowId]);

  if (!isOpen || !workflowId) return null;

  const workflow = workflows.find((w) => w.workflow_id === workflowId);

  if (!workflow) return null;

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{config.domain === 'travel' ? '✈️' : '🏥'}</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">{capitalize(terminology.workflow)} Details</h2>
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
          {/* Workflow Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Workflow ID
              </label>
              <p className="text-sm font-mono text-gray-600 bg-gray-50 px-3 py-2 rounded border">
                {workflow.workflow_id}
              </p>
            </div>

            {workflow.departure_date && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Departure Date
                </label>
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  📅 {formatDate(workflow.departure_date)}
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Total {capitalize(terminology.workflowItems)}
              </label>
              <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                {workflow.item_count} {terminology.workflowItems}
              </p>
            </div>
          </div>

          {/* Workflow Items */}
          <div className="pt-4 border-t">
            <h3 className="font-medium text-gray-900 mb-3">{capitalize(terminology.workflowItems)}</h3>
            
            {loading && (
              <div className="text-center py-8 text-gray-500">
                Loading items...
              </div>
            )}

            {!loading && workflowItems.length === 0 && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <p className="text-gray-500 text-sm">
                  No {terminology.workflowItems} in this {terminology.workflow} yet.
                </p>
              </div>
            )}

            {!loading && workflowItems.length > 0 && (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {workflowItems.map((item) => {
                  const itemId = item.item_id || item.workflow_item_id || item.id;
                  return (
                    <div
                      key={itemId}
                      className="border border-gray-200 rounded-lg p-3 bg-gray-50"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm text-gray-900">
                              {item.kind || 'Item'}
                            </span>
                            {item.status && (
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ${
                                  item.status === 'completed'
                                    ? 'bg-green-100 text-green-700'
                                    : item.status === 'pending'
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-gray-100 text-gray-700'
                                }`}
                              >
                                {item.status}
                              </span>
                            )}
                          </div>
                          <code className="text-xs font-mono text-gray-600 block">
                            {itemId}
                          </code>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
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
