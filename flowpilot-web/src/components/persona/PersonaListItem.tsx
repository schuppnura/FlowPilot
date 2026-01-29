interface Persona {
  persona_id: string;
  user_sub: string;
  title: string;
  scope: string[];
  status: string;
  valid_from: string;
  valid_till: string;
  consent: boolean;
  autobook_price: number;
  autobook_leadtime: number;
  autobook_risklevel: number;
  created_at?: string;
  updated_at?: string;
}

interface PersonaListItemProps {
  persona: Persona;
  isSelected?: boolean;
  onSelect?: (personaId: string) => void;
  onViewDetails?: (personaId: string) => void;
  onEdit?: (personaId: string) => void;
  onToggleStatus?: (personaId: string, currentStatus: string) => void;
}

// Persona icons mapping
const PERSONA_ICONS: Record<string, string> = {
  'traveler': '🛡️',
  'business-traveler': '💼',
  'travel-agent': '👔',
  'office-manager': '📊',
  'booking-assistant': '📋',
  'user-admin': '👤',
};

// Status badge colors
const STATUS_COLORS: Record<string, string> = {
  'active': 'bg-green-100 text-green-800',
  'inactive': 'bg-gray-100 text-gray-800',
  'suspended': 'bg-orange-100 text-orange-800',
  'revoked': 'bg-red-100 text-red-800',
};

export function PersonaListItem({
  persona,
  isSelected = false,
  onSelect,
  onViewDetails,
  onEdit,
  onToggleStatus,
}: PersonaListItemProps) {
  const icon = PERSONA_ICONS[persona.title] || '🎭';
  const statusColor = STATUS_COLORS[persona.status] || 'bg-gray-100 text-gray-800';
  const isActive = persona.status === 'active';

  return (
    <div
      className={`
        border rounded-lg p-4 transition-all
        ${isSelected ? 'border-nura-orange bg-orange-50' : 'border-gray-200 bg-white'}
        hover:shadow-md
      `}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{icon}</span>
          <div>
            <h3 className="font-medium text-gray-900 flex items-center gap-2">
              {persona.title}
              {isSelected && (
                <span className="text-xs bg-nura-orange text-white px-2 py-0.5 rounded">
                  Selected
                </span>
              )}
            </h3>
            <span className={`inline-block text-xs px-2 py-1 rounded-full mt-1 ${statusColor}`}>
              {persona.status.charAt(0).toUpperCase() + persona.status.slice(1)}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-sm mb-3 py-2 border-t border-b border-gray-100">
        <div>
          <span className="text-gray-500">Autobook:</span>
          <span className="ml-1 font-medium">{persona.consent ? '✓' : '✗'}</span>
        </div>
        <div>
          <span className="text-gray-500">Price:</span>
          <span className="ml-1 font-medium">€{persona.autobook_price}</span>
        </div>
        <div>
          <span className="text-gray-500">Days:</span>
          <span className="ml-1 font-medium">{persona.autobook_leadtime}</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {onSelect && isActive && (
          <button
            onClick={() => onSelect(persona.persona_id)}
            className={`
              text-xs px-3 py-1.5 rounded-lg transition-colors
              ${
                isSelected
                  ? 'bg-nura-orange text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }
            `}
          >
            {isSelected ? 'Selected for Workflows' : 'Use for Workflows'}
          </button>
        )}
        
        {onViewDetails && (
          <button
            onClick={() => onViewDetails(persona.persona_id)}
            className="text-xs px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            View Details
          </button>
        )}
        
        {onEdit && (
          <button
            onClick={() => onEdit(persona.persona_id)}
            className="text-xs px-3 py-1.5 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition-colors"
          >
            Edit
          </button>
        )}
        
        {onToggleStatus && (
          <button
            onClick={() => onToggleStatus(persona.persona_id, persona.status)}
            className={`
              text-xs px-3 py-1.5 rounded-lg transition-colors
              ${
                isActive
                  ? 'bg-orange-100 text-orange-700 hover:bg-orange-200'
                  : 'bg-green-100 text-green-700 hover:bg-green-200'
              }
            `}
          >
            {isActive ? 'Deactivate' : 'Activate'}
          </button>
        )}
      </div>
    </div>
  );
}
