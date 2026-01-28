import { terminology } from '../../config';

interface TripListItemProps {
  workflow: {
    workflow_id: string;
    departure_date?: string;
    item_count: number;
  };
  isSelected: boolean;
  onSelect: (workflowId: string) => void;
  onViewDetails: (workflowId: string) => void;
  onShare: (workflowId: string) => void;
  onBook: (workflowId: string) => void;
}

export function TripListItem({ workflow, isSelected, onSelect, onViewDetails, onShare, onBook }: TripListItemProps) {
  return (
    <div
      className={`border rounded-lg p-4 transition-colors ${
        isSelected
          ? 'border-nura-orange bg-orange-50'
          : 'border-gray-200 hover:border-gray-300'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <code className="text-sm font-mono text-gray-900 bg-gray-100 px-2 py-1 rounded">
              {workflow.workflow_id}
            </code>
            {workflow.departure_date && (
              <span className="text-sm text-gray-600">
                📅 {workflow.departure_date}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">
            {workflow.item_count} {terminology.workflowItems}
          </p>
        </div>
        <div className="flex gap-2">
          {isSelected ? (
            <span className="px-3 py-1.5 bg-green-100 text-green-700 text-xs font-medium rounded-lg">
              Selected
            </span>
          ) : (
            <button
              onClick={() => onSelect(workflow.workflow_id)}
              className="px-3 py-1.5 border border-gray-300 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
            >
              Select
            </button>
          )}
          <button
            onClick={() => onViewDetails(workflow.workflow_id)}
            className="px-3 py-1.5 border border-gray-300 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
          >
            View Details
          </button>
          <button
            onClick={() => onShare(workflow.workflow_id)}
            className="px-3 py-1.5 border border-gray-300 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
          >
            🤝 Share
          </button>
          <button
            onClick={() => onBook(workflow.workflow_id)}
            className="px-3 py-1.5 bg-nura-orange text-white text-xs font-medium rounded-lg hover:bg-opacity-90 transition-colors"
          >
            📅 Book
          </button>
        </div>
      </div>
    </div>
  );
}
