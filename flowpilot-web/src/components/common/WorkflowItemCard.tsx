import type { WorkflowItem } from '../../types/models';
import { StatusBadge } from './StatusBadge';

interface WorkflowItemCardProps {
  item: WorkflowItem;
}

export function WorkflowItemCard({ item }: WorkflowItemCardProps) {
  const formatItemDetails = (item: WorkflowItem): string => {
    const parts: string[] = [];

    if (item.type) {
      parts.push(item.type);
    }
    parts.push(item.title);

    if (item.star_rating) {
      parts.push(`⭐${item.star_rating}`);
    }
    if (item.cuisine) {
      parts.push(item.cuisine);
    }
    if (item.city) {
      parts.push(item.city);
    }
    if (item.neighborhood) {
      parts.push(item.neighborhood);
    }
    if (item.departure_airport) {
      parts.push(`${item.departure_airport}→`);
    }
    if (item.arrival_airport) {
      parts.push(item.arrival_airport);
    }

    return parts.join(' • ');
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-sm text-gray-900">{item.kind}</span>
            <span className="text-gray-400">•</span>
            <span className="text-sm text-gray-700">{formatItemDetails(item)}</span>
          </div>
        </div>
        <StatusBadge status={item.status} />
      </div>
    </div>
  );
}
