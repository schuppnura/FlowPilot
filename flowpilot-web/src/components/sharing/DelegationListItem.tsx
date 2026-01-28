import { DelegationResponse, TravelAgentUser } from '../../types/models';

interface DelegationListItemProps {
  delegation: DelegationResponse;
  allUsers: TravelAgentUser[];
  onViewDetails: (delegation: DelegationResponse) => void;
}

export function DelegationListItem({ delegation, allUsers, onViewDetails }: DelegationListItemProps) {
  // Find delegate user info
  const delegateUser = allUsers.find(u => u.id === delegation.delegate_id);
  const delegateDisplay = delegateUser?.displayName || delegateUser?.email || delegation.delegate_id;
  
  // Format scope
  const scopeText = delegation.scope && delegation.scope.length > 0 
    ? delegation.scope.join(', ') 
    : 'read';
  
  // Determine if it's an invitation (read scope) or delegation (execute scope)
  const isInvitation = delegation.scope.includes('read') && !delegation.scope.includes('execute');
  const type = isInvitation ? 'Invite' : 'Delegate';
  
  // Format expiration date
  const expiresAt = new Date(delegation.expires_at);
  const now = new Date();
  const isExpired = expiresAt < now;
  const daysUntilExpiry = Math.ceil((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Type and User */}
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              isInvitation 
                ? 'bg-blue-100 text-blue-700' 
                : 'bg-purple-100 text-purple-700'
            }`}>
              {type}
            </span>
            <span className="font-semibold text-gray-900 truncate">
              {delegateDisplay}
            </span>
          </div>
          
          {/* Details */}
          <div className="space-y-1 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Scope:</span>
              <span className="text-gray-900 font-mono text-xs">{scopeText}</span>
            </div>
            
            {delegation.workflow_id && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">Workflow:</span>
                <code className="text-gray-900 font-mono text-xs truncate">
                  {delegation.workflow_id}
                </code>
              </div>
            )}
            
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Expires:</span>
              <span className={`text-xs ${isExpired ? 'text-red-600' : 'text-gray-700'}`}>
                {isExpired 
                  ? `Expired (${expiresAt.toLocaleDateString()})` 
                  : `${expiresAt.toLocaleDateString()} (${daysUntilExpiry} day${daysUntilExpiry !== 1 ? 's' : ''})`}
              </span>
            </div>
          </div>
        </div>
        
        {/* View Details Button */}
        <button
          onClick={() => onViewDetails(delegation)}
          className="px-3 py-1.5 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap"
        >
          View Details
        </button>
      </div>
    </div>
  );
}
