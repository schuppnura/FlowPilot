import { useAuth } from '../../state/AuthContext';
import { useAppState } from '../../state/AppStateContext';
import { terminology } from '../../config';

interface PanelHeaderProps {
  onSignInClick?: () => void;
}

export function PanelHeader({ onSignInClick }: PanelHeaderProps) {
  const { user, signOut } = useAuth();
  const {
    personas,
    selectedPersona,
    workflows,
    selectedWorkflowId,
  } = useAppState();

  if (!user) {
    return (
      <div className="flex justify-end mb-4">
        <button
          onClick={onSignInClick}
          className="px-4 py-2 bg-nura-orange text-white text-sm font-medium rounded-lg hover:bg-opacity-90 transition-colors"
        >
          Sign In
        </button>
      </div>
    );
  }

  const currentPersonaTitle = selectedPersona?.title || (personas.length > 0 ? personas[0] : null);
  const currentWorkflow = workflows.find((w) => w.workflow_id === selectedWorkflowId);

  return (
    <div className="flex items-center justify-end gap-4 mb-4">
      {/* Current Persona Display */}
      {currentPersonaTitle && (
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-gray-600">Current Persona:</span>
          <span className="px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg font-medium">
            {currentPersonaTitle}{selectedPersona ? `/${selectedPersona.circle}` : ''}
          </span>
        </div>
      )}

      {/* Current Workflow Display */}
      {currentWorkflow && (
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-gray-600">Current {terminology.Workflow}:</span>
          <code className="px-3 py-1.5 bg-gray-50 text-gray-700 rounded-lg font-mono text-xs">
            {currentWorkflow.workflow_id.substring(0, 12)}...
          </code>
        </div>
      )}

      {/* Sign Out Button */}
      <button
        onClick={signOut}
        className="px-4 py-2 bg-gray-600 text-white text-sm font-medium rounded-lg hover:bg-gray-700 transition-colors"
      >
        Sign Out
      </button>
    </div>
  );
}
