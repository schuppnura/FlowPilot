import { useEffect, useState } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { ColdStartNotice } from '../common/ColdStartNotice';
import { PanelHeader } from '../common/PanelHeader';
import { useAuth } from '../../state/AuthContext';
import { CreateTripModal } from '../trip/CreateTripModal';
import { TripListItem } from '../trip/TripListItem';
import { TripDetailsModal } from '../trip/TripDetailsModal';
import { BookTripModal } from '../trip/BookTripModal';
import { config, terminology } from '../../config';

export function MyTripsPanel() {
  const { openSignInModal } = useAuth();
  const {
    workflows,
    selectedWorkflowId,
    workflowTemplates,
    personas,
    loading,
    errorMessage,
    loadWorkflowTemplates,
    loadWorkflows,
    selectWorkflow,
  } = useAppState();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showBookModal, setShowBookModal] = useState(false);
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);

  // Load templates and workflows on mount
  useEffect(() => {
    if (workflowTemplates.length === 0) {
      loadWorkflowTemplates();
    }
    if (workflows.length === 0) {
      loadWorkflows();
    }
  }, []);

  const handleSelectTrip = async (workflowId: string) => {
    await selectWorkflow(workflowId);
  };

  const handleViewDetails = (workflowId: string) => {
    setSelectedTripId(workflowId);
    setShowDetailsModal(true);
  };

  const handleBook = (workflowId: string) => {
    setSelectedTripId(workflowId);
    setShowBookModal(true);
  };

  const personaRequired = personas.length === 0;

  return (
    <div className="space-y-6">
      {/* Panel Header */}
      <PanelHeader onSignInClick={openSignInModal} />

      {/* Error Message */}
      {errorMessage && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {errorMessage}
        </div>
      )}

      {/* My Trips Panel */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-medium text-nura-dark flex items-center gap-3">
            <span className="text-2xl">{config.domain === 'travel' ? '✈️' : '🏥'}</span>
            {terminology.Workflows}
          </h2>
          <button
            className="px-4 py-2 bg-nura-orange text-white text-sm font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50"
            onClick={() => setShowCreateModal(true)}
            disabled={personaRequired || loading}
          >
            + Create New
          </button>
        </div>

        {personaRequired && (
          <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
            <p className="text-sm text-orange-700">
              ⚠️ Please select a persona first
            </p>
          </div>
        )}

        {loading && (
          <div>
            <ColdStartNotice
              isLoading={loading}
              delayThresholdMs={3000}
              message="Services are waking up from hibernation. This may take 10-30 seconds on first use. Please wait..."
            />
            <div className="text-center py-8 text-gray-500">
              Loading {terminology.workflows}...
            </div>
          </div>
        )}

        {!loading && workflows.length === 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <p className="text-gray-500 text-sm">
              No {terminology.workflows} available. Create a {terminology.workflow} using the button above.
            </p>
          </div>
        )}

        {!loading && workflows.length > 0 && (
          <div className="space-y-3">
            {workflows.map((workflow) => (
              <TripListItem
                key={workflow.workflow_id}
                workflow={workflow}
                isSelected={workflow.workflow_id === selectedWorkflowId}
                onSelect={handleSelectTrip}
                onViewDetails={handleViewDetails}
                onBook={handleBook}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create Trip Modal */}
      <CreateTripModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
      />

      {/* Trip Details Modal */}
      <TripDetailsModal
        workflowId={selectedTripId}
        isOpen={showDetailsModal}
        onClose={() => {
          setShowDetailsModal(false);
          setSelectedTripId(null);
        }}
      />

      {/* Book Trip Modal */}
      <BookTripModal
        workflowId={selectedTripId}
        isOpen={showBookModal}
        onClose={() => {
          setShowBookModal(false);
          setSelectedTripId(null);
        }}
      />
    </div>
  );
}
