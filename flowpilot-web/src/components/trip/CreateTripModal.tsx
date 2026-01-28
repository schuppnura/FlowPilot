import { useState } from 'react';
import { useAppState } from '../../state/AppStateContext';
import { terminology, capitalize } from '../../config';

interface CreateTripModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateTripModal({ isOpen, onClose }: CreateTripModalProps) {
  const {
    workflowTemplates,
    selectedPersona,
    personas,
    principalSub,
    loading,
    createWorkflow,
  } = useAppState();

  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const [startDate, setStartDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!selectedTemplateId || !principalSub) return;

    const persona = selectedPersona || (personas.length > 0 ? personas[0] : undefined);
    console.log('CreateTripModal: Creating workflow with:', {
      selectedPersona,
      personas,
      resolvedPersona: persona,
      templateId: selectedTemplateId,
    });

    if (!persona) {
      alert('No persona selected. Please select a persona from My Account.');
      return;
    }

    await createWorkflow({
      template_id: selectedTemplateId,
      principal_sub: principalSub,
      start_date: startDate,
      persona,
    });

    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xl font-medium text-gray-900">Create New {capitalize(terminology.workflow)}</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl"
            >
              ×
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {capitalize(terminology.workflow)} template
              </label>
              <select
                value={selectedTemplateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
              >
                <option value="">Choose a {terminology.workflow} template...</option>
                {workflowTemplates.map((template) => (
                  <option key={template.template_id} value={template.template_id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Start date
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent disabled:opacity-50"
              />
            </div>
          </div>

          <div className="flex gap-3 mt-6">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!selectedTemplateId || loading}
              className="flex-1 px-4 py-2 bg-nura-orange text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
