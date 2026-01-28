import { useState, useEffect } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { terminology, capitalize } from '../../config';

interface ShareTripModalProps {
  workflowId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

type ShareTab = 'invite' | 'delegate';

export function ShareTripModal({ workflowId, isOpen, onClose }: ShareTripModalProps) {
  const {
    workflows,
    principalSub,
    allUsers,
    loading,
    errorMessage,
    statusMessage,
    loadAllUsers,
    createInvitation,
    createDelegation,
    clearError,
    setStatus,
  } = useAppState();

  const [activeTab, setActiveTab] = useState<ShareTab>('invite');
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [expiresInDays, setExpiresInDays] = useState<number>(30);

  // Load users on mount and clear messages when modal opens
  useEffect(() => {
    if (isOpen) {
      clearError();
      setStatus('');
      if (allUsers.length === 0) {
        loadAllUsers();
      }
    }
  }, [isOpen, allUsers.length, loadAllUsers, clearError, setStatus]);

  if (!isOpen || !workflowId || !principalSub) return null;

  const workflow = workflows.find((w) => w.workflow_id === workflowId);
  if (!workflow) return null;

  const handleShare = async () => {
    if (!selectedUserId) return;

    const request = {
      principal_id: principalSub,
      delegate_id: selectedUserId,
      workflow_id: workflowId,
      scope: activeTab === 'invite' ? ['read'] : ['execute'],
      expires_in_days: expiresInDays,
    };

    if (activeTab === 'invite') {
      await createInvitation(request);
    } else {
      await createDelegation(request);
    }

    // Reset and close
    setSelectedUserId(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🤝</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">Share {capitalize(terminology.workflow)}</h2>
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

        {/* Tabs */}
        <div className="flex border-b">
          <button
            onClick={() => setActiveTab('invite')}
            className={`flex-1 px-6 py-3 font-medium transition-colors ${
              activeTab === 'invite'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
            }`}
          >
            ✉️ Invite
          </button>
          <button
            onClick={() => setActiveTab('delegate')}
            className={`flex-1 px-6 py-3 font-medium transition-colors ${
              activeTab === 'delegate'
                ? 'text-purple-600 border-b-2 border-purple-600 bg-purple-50'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
            }`}
          >
            🤝 Delegate
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Error Message */}
          {errorMessage && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              {errorMessage}
            </div>
          )}

          {/* Success Message */}
          {statusMessage && (
            <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
              {statusMessage}
            </div>
          )}
          {/* Explanatory Text */}
          <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
            {activeTab === 'invite' ? (
              <div>
                <h3 className="font-semibold text-gray-900 mb-2">What is an Invitation?</h3>
                <p className="text-sm text-gray-700 mb-2">
                  An <strong>invitation</strong> grants <strong>read-only</strong> access to view this {terminology.workflow} and its items. 
                  The invitee can see all details but cannot execute or modify anything.
                </p>
                <p className="text-sm text-gray-600">
                  Use this when you want someone to review your {terminology.workflow} without giving them permission to make changes.
                </p>
              </div>
            ) : (
              <div>
                <h3 className="font-semibold text-gray-900 mb-2">What is a Delegation?</h3>
                <p className="text-sm text-gray-700 mb-2">
                  A <strong>delegation</strong> grants <strong>execute</strong> permission to perform actions on your behalf. 
                  The delegate can execute workflow items as if they were you, the {terminology.workflow} owner.
                </p>
                <p className="text-sm text-gray-600">
                  Use this when you want someone to handle bookings or other actions for your {terminology.workflow}.
                </p>
              </div>
            )}
          </div>

          {/* Demo Disclaimer */}
          <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm text-yellow-800">
              <strong>Demo Mode:</strong> In this demo, you can select any user from the list below. 
              In a real product, users would be identified by their username and properly authenticated.
            </p>
          </div>

          {/* User Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select User
            </label>
            {loading && allUsers.length === 0 ? (
              <p className="text-sm text-gray-500">Loading users...</p>
            ) : (
              <select
                value={selectedUserId || ''}
                onChange={(e) => setSelectedUserId(e.target.value || null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">-- Select a user --</option>
                {allUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.displayName || user.email || user.username}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Expiration */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Expires in (days)
            </label>
            <input
              type="number"
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(parseInt(e.target.value) || 1)}
              min="1"
              max="365"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              The {activeTab === 'invite' ? 'invitation' : 'delegation'} will expire after this many days.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleShare}
            disabled={!selectedUserId || loading}
            className={`px-4 py-2 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              activeTab === 'invite'
                ? 'bg-blue-600 hover:bg-blue-700'
                : 'bg-purple-600 hover:bg-purple-700'
            }`}
          >
            {activeTab === 'invite' ? 'Send Invitation' : 'Create Delegation'}
          </button>
        </div>
      </div>
    </div>
  );
}
