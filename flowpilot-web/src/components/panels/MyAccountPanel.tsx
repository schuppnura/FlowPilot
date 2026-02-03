import { useState, useEffect } from 'react';
import { useAuth } from '../../state/AuthContext';
import { useAppState } from '../../state/AppStateContext';
import { PersonaListItem } from '../persona/PersonaListItem';
import { PersonaDetailsModal } from '../persona/PersonaDetailsModal';
import { CreatePersonaModal } from '../persona/CreatePersonaModal';
import { ColdStartNotice } from '../common/ColdStartNotice';
import { PanelHeader } from '../common/PanelHeader';
import { UserProfileClient } from '../../services/api/userProfile';
import { AuthZClient } from '../../services/api/authz';

interface Persona {
  persona_id: string;
  user_sub: string;
  title: string;
  circle: string;
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

export function MyAccountPanel() {
  const { user, loading: authLoading, openSignInModal, getToken } = useAuth();
  const { personas, selectedPersona, setSelectedPersona, reloadPersonas } = useAppState();
  const [personasDetailed, setPersonasDetailed] = useState<Persona[]>([]);
  const [loadingPersonas, setLoadingPersonas] = useState(false);
  const [personasError, setPersonasError] = useState<string | null>(null);
  const [selectedPersonaForModal, setSelectedPersonaForModal] = useState<Persona | null>(null);
  const [modalMode, setModalMode] = useState<'view' | 'edit'>('view');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [personaValidationWarning, setPersonaValidationWarning] = useState<string | null>(null);
  
  // Initialize API clients
  const userProfileClient = new UserProfileClient(getToken, openSignInModal);
  const authzClient = new AuthZClient(getToken, openSignInModal);

  // Fetch detailed personas when user is authenticated
  useEffect(() => {
    if (!authLoading && user) {
      loadPersonas();
    }
  }, [authLoading, user]);

  const validateFirstPersona = async (persona: Persona) => {
    if (!user) return;
    
    try {
      console.log('Validating first persona via authz-api:', persona);
      const result = await authzClient.validatePersona(
        user.uid,
        persona.title,
        {
          status: persona.status,
          valid_from: persona.valid_from,
          valid_till: persona.valid_till,
        }
      );
      
      console.log('Persona validation result:', result);
      
      // If persona is invalid, show warning
      if (result.decision === 'deny') {
        setPersonaValidationWarning(
          `Your persona "${persona.title}" is not currently valid. ` +
          `Without a valid active persona, you cannot create workflows or perform any operations. ` +
          `Please activate this persona or create a new active one.`
        );
      } else {
        // Persona is valid - clear any previous warning
        setPersonaValidationWarning(null);
      }
    } catch (error: any) {
      console.error('Failed to validate persona:', error);
      // Don't show error to user - validation is best-effort
    }
  };

  const loadPersonas = async () => {
    setLoadingPersonas(true);
    setPersonasError(null);
    setPersonaValidationWarning(null);
    try {
      const detailed = await userProfileClient.getPersonasDetailed();
      setPersonasDetailed(detailed);
      
      // Auto-open create modal if no personas exist
      if (detailed.length === 0) {
        setShowCreateModal(true);
      }
      
      // If this is the first and only persona, validate it via authz-api
      console.log('MyAccountPanel: Checking if should validate persona. Length:', detailed.length, 'User:', !!user);
      if (detailed.length === 1 && user) {
        console.log('MyAccountPanel: Will validate first persona');
        await validateFirstPersona(detailed[0]);
      } else {
        console.log('MyAccountPanel: Skipping validation - need exactly 1 persona, have', detailed.length);
      }
    } catch (error: any) {
      console.error('Failed to load personas:', error);
      setPersonasError(error.message || 'Failed to load personas');
    } finally {
      setLoadingPersonas(false);
    }
  };

  const handleToggleStatus = async (personaId: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
    try {
      await userProfileClient.updatePersona(personaId, { status: newStatus });
      await loadPersonas(); // Reload list (this will re-validate if needed)
    } catch (error: any) {
      alert(`Failed to update persona: ${error.message}`);
    }
  };

  const handleViewDetails = (personaId: string) => {
    const persona = personasDetailed.find((p) => p.persona_id === personaId);
    if (persona) {
      setSelectedPersonaForModal(persona);
      setModalMode('view');
    }
  };

  const handleEdit = (personaId: string) => {
    const persona = personasDetailed.find((p) => p.persona_id === personaId);
    if (persona) {
      setSelectedPersonaForModal(persona);
      setModalMode('edit');
    }
  };

  const handleSavePersona = async (personaId: string, updates: Partial<Persona>) => {
    await userProfileClient.updatePersona(personaId, updates);
    await loadPersonas(); // Reload list to reflect changes
  };

  const handleCreatePersona = async (personaData: any) => {
    try {
      const isFirstPersona = personasDetailed.length === 0;
      await userProfileClient.createPersona(personaData);
      await loadPersonas(); // Reload list to include new persona
      
      // Auto-select the first persona for workflows
      if (isFirstPersona) {
        setSelectedPersona({ title: personaData.title, circle: personaData.circle });
      }
      
      // Reload personas in AppStateContext so other tabs see the new persona
      await reloadPersonas();
      
      setPersonasError(null); // Clear any previous errors
    } catch (error: any) {
      // Parse error message for user-friendly display
      let userMessage = error.message || 'Failed to create persona';
      
      // Check for duplicate persona
      if (userMessage.toLowerCase().includes('already exists') || 
          userMessage.toLowerCase().includes('duplicate')) {
        userMessage = `A persona with this title already exists. Please choose a different title or deactivate the existing persona.`;
      }
      
      setPersonasError(userMessage);
      throw error; // Re-throw so the modal can also handle it
    }
  };

  // Debug logging
  useEffect(() => {
    console.log('MyAccountPanel: personas:', personas, 'selectedPersona:', selectedPersona);
  }, [personas, selectedPersona]);

  return (
    <div className="space-y-6">
      {/* Panel Header */}
      <PanelHeader onSignInClick={openSignInModal} />
      
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-medium text-nura-dark flex items-center gap-3">
            <span className="text-2xl">👤</span>
            My Personas
          </h2>
          <button
            className="px-4 py-2 bg-nura-orange text-white text-sm font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50"
            onClick={() => setShowCreateModal(true)}
            disabled={personasDetailed.length >= 5}
          >
            + Create New
          </button>
        </div>

        {loadingPersonas && (
              <div>
                <ColdStartNotice
                  isLoading={loadingPersonas}
                  delayThresholdMs={3000}
                  message="Services are waking up from hibernation. This may take 10-30 seconds on first use. Please wait..."
                />
                <div className="text-center py-8 text-gray-500">
                  Loading personas...
                </div>
              </div>
            )}

            {personaValidationWarning && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-700 mb-4">
                {personaValidationWarning}
              </div>
            )}

            {personasError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                {personasError}
              </div>
            )}

            {!loadingPersonas && !personasError && personasDetailed.length === 0 && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <p className="text-green-700">
                  Please add a persona to your account.
                </p>
              </div>
            )}

            {!loadingPersonas && !personasError && personasDetailed.length > 0 && (
              <div className="space-y-3">
                {personasDetailed.map((persona) => (
                  <PersonaListItem
                    key={persona.persona_id}
                    persona={persona}
                    isSelected={(() => {
                      const isSelected = selectedPersona !== null &&
                        persona.title === selectedPersona.title &&
                        persona.circle === selectedPersona.circle;
                      console.log(`PersonaListItem ${persona.title}/${persona.circle}: isSelected=${isSelected}, selectedPersona=`, selectedPersona);
                      return isSelected;
                    })()}
                    onSelect={(id) => {
                      const p = personasDetailed.find((p) => p.persona_id === id);
                      if (p) setSelectedPersona({ title: p.title, circle: p.circle });
                    }}
                    onViewDetails={handleViewDetails}
                    onEdit={handleEdit}
                    onToggleStatus={handleToggleStatus}
                  />
                ))}
              </div>
            )}

        {/* Persona Details Modal */}
        {selectedPersonaForModal && (
          <PersonaDetailsModal
            persona={selectedPersonaForModal}
            isOpen={!!selectedPersonaForModal}
            mode={modalMode}
            onClose={() => setSelectedPersonaForModal(null)}
            onSave={handleSavePersona}
          />
        )}

        {/* Create Persona Modal */}
        <CreatePersonaModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreatePersona}
          existingTitles={personasDetailed.map((p) => p.title)}
          currentPersonaCount={personasDetailed.length}
        />
      </div>
    </div>
  );
}
