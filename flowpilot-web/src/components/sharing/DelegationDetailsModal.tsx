import { useState } from 'react';
import { DelegationResponse, TravelAgentUser } from '../../types/models';

interface DelegationDetailsModalProps {
  delegation: DelegationResponse | null;
  allUsers: TravelAgentUser[];
  isOpen: boolean;
  onClose: () => void;
  onRevoke: (delegationId: string) => Promise<void>;
}

export function DelegationDetailsModal({ 
  delegation, 
  allUsers, 
  isOpen, 
  onClose, 
  onRevoke 
}: DelegationDetailsModalProps) {
  const [isRevoking, setIsRevoking] = useState(false);

  if (!isOpen || !delegation) return null;

  // Find delegate user info
  const delegateUser = allUsers.find(u => u.id === delegation.delegate_id);
  const delegateDisplay = delegateUser?.displayName || delegateUser?.email || delegation.delegate_id;
  
  // Format scope
  const scopeText = delegation.scope && delegation.scope.length > 0 
    ? delegation.scope.join(', ') 
    : 'read';
  
  // Determine if it's an invitation (read scope) or delegation (execute scope)
  const isInvitation = delegation.scope.includes('read') && !delegation.scope.includes('execute');
  const type = isInvitation ? 'Invitation' : 'Delegation';
  
  // Format expiration date
  const expiresAt = new Date(delegation.expires_at);
  const now = new Date();
  const isExpired = expiresAt < now;
  const daysUntilExpiry = Math.ceil((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

  const handleRevoke = async () => {
    console.log('DelegationDetailsModal.handleRevoke: Button clicked, delegation:', delegation);
    
    if (!delegation.delegation_id) {
      console.error('DelegationDetailsModal.handleRevoke: No delegation_id found!');
      return;
    }
    
    console.log('DelegationDetailsModal.handleRevoke: Calling onRevoke with ID:', delegation.delegation_id);
    setIsRevoking(true);
    try {
      await onRevoke(delegation.delegation_id);
      console.log('DelegationDetailsModal.handleRevoke: onRevoke completed successfully');
      onClose();
    } catch (error) {
      console.error('DelegationDetailsModal.handleRevoke: Error during revoke:', error);
      // Error is handled by parent
    } finally {
      setIsRevoking(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{isInvitation ? '✉️' : '🤝'}</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">{type} Details</h2>
              <span className="text-sm text-gray-500">{delegateDisplay}</span>
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
        <div className="p-6 space-y-4">
          {/* Type Badge */}
          <div>
            <span className={`inline-block text-sm px-3 py-1 rounded-full ${
              isInvitation 
                ? 'bg-blue-100 text-blue-700' 
                : 'bg-purple-100 text-purple-700'
            }`}>
              {type}
            </span>
          </div>

          {/* Details Grid */}
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <span className="text-sm font-medium text-gray-500">Principal:</span>
              <code className="col-span-2 text-sm font-mono text-gray-900 break-all">
                {delegation.principal_id}
              </code>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <span className="text-sm font-medium text-gray-500">Delegate:</span>
              <div className="col-span-2">
                <div className="text-sm text-gray-900">{delegateDisplay}</div>
                <code className="text-xs font-mono text-gray-500 break-all">
                  {delegation.delegate_id}
                </code>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <span className="text-sm font-medium text-gray-500">Scope:</span>
              <code className="col-span-2 text-sm font-mono text-gray-900">
                {scopeText}
              </code>
            </div>

            {delegation.workflow_id && (
              <div className="grid grid-cols-3 gap-2">
                <span className="text-sm font-medium text-gray-500">Workflow:</span>
                <code className="col-span-2 text-sm font-mono text-gray-900 break-all">
                  {delegation.workflow_id}
                </code>
              </div>
            )}

            {!delegation.workflow_id && (
              <div className="grid grid-cols-3 gap-2">
                <span className="text-sm font-medium text-gray-500">Workflow:</span>
                <span className="col-span-2 text-sm text-gray-500 italic">
                  All workflows
                </span>
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <span className="text-sm font-medium text-gray-500">Expires:</span>
              <div className="col-span-2">
                <div className={`text-sm ${isExpired ? 'text-red-600' : 'text-gray-900'}`}>
                  {expiresAt.toLocaleDateString()} {expiresAt.toLocaleTimeString()}
                </div>
                <div className={`text-xs ${isExpired ? 'text-red-600' : 'text-gray-500'}`}>
                  {isExpired 
                    ? 'Expired' 
                    : `${daysUntilExpiry} day${daysUntilExpiry !== 1 ? 's' : ''} remaining`}
                </div>
              </div>
            </div>

            {delegation.delegation_id && (
              <div className="grid grid-cols-3 gap-2">
                <span className="text-sm font-medium text-gray-500">Delegation ID:</span>
                <code className="col-span-2 text-xs font-mono text-gray-500 break-all">
                  {delegation.delegation_id}
                </code>
              </div>
            )}
          </div>

          {/* Explanatory Text */}
          <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
            <p className="text-sm text-gray-700">
              {isInvitation ? (
                <>
                  <strong>Invitation</strong> grants <strong>read</strong> access to view workflow details. 
                  The invitee can see the workflow and its items but cannot execute or modify them.
                </>
              ) : (
                <>
                  <strong>Delegation</strong> grants <strong>execute</strong> access to perform actions on behalf of the principal. 
                  The delegate can execute workflow items as if they were the workflow owner.
                </>
              )}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center gap-3 p-6 border-t bg-gray-50">
          <button
            onClick={handleRevoke}
            disabled={isRevoking || isExpired}
            className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isRevoking ? 'Revoking...' : 'Revoke'}
          </button>
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
