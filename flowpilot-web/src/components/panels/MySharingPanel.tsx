import { useEffect, useState } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { DelegationListItem } from '../sharing/DelegationListItem';
import { DelegationDetailsModal } from '../sharing/DelegationDetailsModal';
import { DelegationResponse } from '../../types/models';
import { terminology, capitalize } from '../../config';

export function MySharingPanel() {
  const {
    delegations,
    allUsers,
    loading,
    errorMessage,
    statusMessage,
    clearError,
    loadDelegations,
    loadAllUsers,
    revokeDelegation,
  } = useAppState();

  const [selectedDelegation, setSelectedDelegation] = useState<DelegationResponse | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);

  // Load data on mount
  useEffect(() => {
    loadDelegations();
    loadAllUsers();
  }, []);

  const handleViewDetails = (delegation: DelegationResponse) => {
    setSelectedDelegation(delegation);
    setIsDetailsModalOpen(true);
  };

  const handleCloseDetails = () => {
    setIsDetailsModalOpen(false);
    setSelectedDelegation(null);
  };

  const handleRevoke = async (delegationId: string) => {
    await revokeDelegation(delegationId);
    handleCloseDetails();
  };

  // Sort delegations by workflow_id
  const sortedDelegations = [...delegations].sort((a, b) => {
    // Delegations without workflow_id go first
    if (!a.workflow_id && !b.workflow_id) return 0;
    if (!a.workflow_id) return -1;
    if (!b.workflow_id) return 1;
    return a.workflow_id.localeCompare(b.workflow_id);
  });

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-medium text-gray-900 mb-2">My Sharing</h1>
        <p className="text-gray-600">
          Manage all your {terminology.workflow} invitations and delegations in one place.
        </p>
      </div>

      {/* Status/Error Messages */}
      {errorMessage && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
          <span className="text-red-700 flex-1">{errorMessage}</span>
          <button
            onClick={clearError}
            className="text-red-400 hover:text-red-600"
          >
            ×
          </button>
        </div>
      )}

      {statusMessage && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-green-700 whitespace-pre-line">{statusMessage}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && delegations.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-500">Loading your sharing relationships...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && delegations.length === 0 && (
        <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
          <span className="text-5xl mb-4 block">🤝</span>
          <h2 className="text-xl font-medium text-gray-900 mb-2">
            No sharing relationships yet
          </h2>
          <p className="text-gray-600 mb-4">
            You haven't invited anyone or delegated any {terminology.workflows} yet.
          </p>
          <p className="text-sm text-gray-500">
            Go to "My {capitalize(terminology.workflows)}" to share a {terminology.workflow} with others.
          </p>
        </div>
      )}

      {/* Delegations List */}
      {!loading && delegations.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-600">
              {delegations.length} sharing relationship{delegations.length !== 1 ? 's' : ''}
            </p>
          </div>

          {sortedDelegations.map((delegation) => (
            <DelegationListItem
              key={delegation.delegation_id || `${delegation.delegate_id}-${delegation.workflow_id}`}
              delegation={delegation}
              allUsers={allUsers}
              onViewDetails={handleViewDetails}
            />
          ))}
        </div>
      )}

      {/* Delegation Details Modal */}
      <DelegationDetailsModal
        delegation={selectedDelegation}
        allUsers={allUsers}
        isOpen={isDetailsModalOpen}
        onClose={handleCloseDetails}
        onRevoke={handleRevoke}
      />
    </div>
  );
}
