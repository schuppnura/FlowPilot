import { useState, useEffect } from 'react';
import { useAuth } from '../../state/AuthContext';
import { useAppState } from '../../state/AppStateContext';
import { SignInForm } from '../common/SignInForm';
import { SignUpForm } from '../common/SignUpForm';
import { PersonaListItem } from '../persona/PersonaListItem';
import { PersonaDetailsModal } from '../persona/PersonaDetailsModal';
import { CreatePersonaModal } from '../persona/CreatePersonaModal';
import { ColdStartNotice } from '../common/ColdStartNotice';
import { UserProfileClient } from '../../services/api/userProfile';

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

type Tab = 'profile' | 'personas';

export function MyAccountPanel() {
  const { user, signOut, getToken } = useAuth();
  const { personas, selectedPersona, setSelectedPersona } = useAppState();
  const [isSignUp, setIsSignUp] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('profile');
  const [personasDetailed, setPersonasDetailed] = useState<Persona[]>([]);
  const [loadingPersonas, setLoadingPersonas] = useState(false);
  const [personasError, setPersonasError] = useState<string | null>(null);
  const [selectedPersonaForModal, setSelectedPersonaForModal] = useState<Persona | null>(null);
  const [modalMode, setModalMode] = useState<'view' | 'edit'>('view');
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  // Initialize UserProfileClient
  const userProfileClient = new UserProfileClient(getToken);

  // Fetch detailed personas when tab changes to personas
  useEffect(() => {
    if (activeTab === 'personas' && user) {
      loadPersonas();
    }
  }, [activeTab, user]);

  const loadPersonas = async () => {
    setLoadingPersonas(true);
    setPersonasError(null);
    try {
      const detailed = await userProfileClient.getPersonasDetailed();
      setPersonasDetailed(detailed);
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
      await loadPersonas(); // Reload list
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
    await userProfileClient.createPersona(personaData);
    await loadPersonas(); // Reload list to include new persona
  };

  // Debug logging
  useEffect(() => {
    console.log('MyAccountPanel: personas:', personas, 'selectedPersona:', selectedPersona);
  }, [personas, selectedPersona]);

  if (user) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-medium text-nura-dark flex items-center gap-3">
            <span className="text-2xl">👤</span>
            My account
          </h2>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-4 border-b border-gray-200 mb-6">
          <button
            onClick={() => setActiveTab('profile')}
            className={`
              pb-3 px-1 font-medium transition-colors relative
              ${activeTab === 'profile' ? 'text-nura-orange' : 'text-gray-500 hover:text-gray-700'}
            `}
          >
            Profile
            {activeTab === 'profile' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-nura-orange" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('personas')}
            className={`
              pb-3 px-1 font-medium transition-colors relative
              ${activeTab === 'personas' ? 'text-nura-orange' : 'text-gray-500 hover:text-gray-700'}
            `}
          >
            Personas
            {activeTab === 'personas' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-nura-orange" />
            )}
          </button>
        </div>

        {/* Profile Tab Content */}
        {activeTab === 'profile' && (
          <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-500">Email</label>
            <p className="text-base text-gray-900">{user.email}</p>
          </div>

          <div>
            <label className="text-sm text-gray-500">User ID</label>
            <p className="text-base font-mono text-gray-700 select-all">{user.uid}</p>
          </div>

          {personas.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {personas.length > 1 ? 'User persona' : 'Persona'}
              </label>
              {personas.length > 1 ? (
                <select
                  value={selectedPersona || personas[0] || ''}
                  onChange={(e) => {
                    const newPersona = e.target.value;
                    console.log('MyAccountPanel: Changing persona from', selectedPersona, 'to', newPersona);
                    if (newPersona) {
                      setSelectedPersona(newPersona);
                    }
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
                >
                  {personas.map((persona) => (
                    <option key={persona} value={persona}>
                      {persona} {persona === selectedPersona ? '(selected)' : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg">
                  <span className="text-lg">🛡️</span>
                  <span className="text-base text-gray-900">{personas[0]}</span>
                </div>
              )}
              {/* Debug info */}
              {process.env.NODE_ENV === 'development' && (
                <div className="mt-2 text-xs text-gray-500">
                  Debug: personas={JSON.stringify(personas)}, selectedPersona={selectedPersona || 'null'}
                </div>
              )}
            </div>
          )}
          {personas.length === 0 && user && (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-700">
                ⚠️ No personas found for your account. Please contact support to have personas created.
              </p>
            </div>
          )}

            <div className="pt-4 border-t">
              <button
                onClick={signOut}
                className="px-6 py-2 bg-nura-orange text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>
        )}

        {/* Personas Tab Content */}
        {activeTab === 'personas' && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-gray-900">My Personas</h3>
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

            {personasError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                {personasError}
              </div>
            )}

            {!loadingPersonas && !personasError && personasDetailed.length === 0 && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <p className="text-yellow-700">
                  No personas found. This shouldn't happen if you signed up correctly.
                </p>
              </div>
            )}

            {!loadingPersonas && !personasError && personasDetailed.length > 0 && (
              <div className="space-y-3">
                {personasDetailed.map((persona) => (
                  <PersonaListItem
                    key={persona.persona_id}
                    persona={persona}
                    isSelected={persona.title === selectedPersona}
                    onSelect={(id) => {
                      const p = personasDetailed.find((p) => p.persona_id === id);
                      if (p) setSelectedPersona(p.title);
                    }}
                    onViewDetails={handleViewDetails}
                    onEdit={handleEdit}
                    onToggleStatus={handleToggleStatus}
                  />
                ))}
              </div>
            )}
          </div>
        )
        }

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
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 max-w-md mx-auto">
      <h2 className="text-2xl font-medium text-nura-dark mb-6 flex items-center gap-3">
        <span className="text-2xl">👤</span>
        {isSignUp ? 'Sign up' : 'Sign in'}
      </h2>

      <div className="mb-4">
        <button
          onClick={() => setIsSignUp(!isSignUp)}
          className="text-sm text-nura-orange hover:underline"
        >
          {isSignUp
            ? 'Already have an account? Sign in'
            : "Don't have an account? Sign up"}
        </button>
      </div>

      {isSignUp ? <SignUpForm /> : <SignInForm />}
    </div>
  );
}
