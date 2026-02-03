import { useState, useEffect } from 'react';

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

interface PersonaDetailsModalProps {
  persona: Persona;
  isOpen: boolean;
  mode: 'view' | 'edit';
  onClose: () => void;
  onSave?: (personaId: string, updates: Partial<Persona>) => Promise<void>;
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

export function PersonaDetailsModal({
  persona,
  isOpen,
  mode,
  onClose,
  onSave,
}: PersonaDetailsModalProps) {
  const [isEditing, setIsEditing] = useState(mode === 'edit');
  const [formData, setFormData] = useState({
    circle: persona.circle,
    status: persona.status,
    consent: persona.consent,
    autobook_price: persona.autobook_price,
    autobook_leadtime: persona.autobook_leadtime,
    autobook_risklevel: persona.autobook_risklevel,
    valid_from: persona.valid_from,
    valid_till: persona.valid_till,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setIsEditing(mode === 'edit');
    setFormData({
      circle: persona.circle,
      status: persona.status,
      consent: persona.consent,
      autobook_price: persona.autobook_price,
      autobook_leadtime: persona.autobook_leadtime,
      autobook_risklevel: persona.autobook_risklevel,
      valid_from: persona.valid_from,
      valid_till: persona.valid_till,
    });
    setErrors({});
  }, [persona, mode, isOpen]);

  if (!isOpen) return null;

  const icon = PERSONA_ICONS[persona.title] || '🎭';

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Circle required
    if (!formData.circle || formData.circle.trim() === '') {
      newErrors.circle = 'Circle is required';
    }

    if (formData.autobook_price <= 0) {
      newErrors.autobook_price = 'Price must be a positive number';
    }

    if (formData.autobook_leadtime <= 0) {
      newErrors.autobook_leadtime = 'Lead time must be a positive number of days';
    }

    if (formData.autobook_risklevel < 0 || formData.autobook_risklevel > 100) {
      newErrors.autobook_risklevel = 'Risk level must be between 0 and 100';
    }

    // Validate valid_till comes after valid_from (logical consistency check)
    const validFrom = new Date(formData.valid_from);
    const validTill = new Date(formData.valid_till);
    if (validTill <= validFrom) {
      newErrors.valid_till = 'Valid Until must be after Valid From';
    }

    // NOTE: We don't check if dates are in the past/future - only relative to each other
    // The backend PEP/PDP will enforce lifecycle policies based on current time

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validateForm()) return;
    if (!onSave) return;

    setIsSaving(true);
    try {
      await onSave(persona.persona_id, formData);
      setIsEditing(false);
      onClose();
    } catch (error: any) {
      setErrors({ general: error.message || 'Failed to save changes' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      circle: persona.circle,
      status: persona.status,
      consent: persona.consent,
      autobook_price: persona.autobook_price,
      autobook_leadtime: persona.autobook_leadtime,
      autobook_risklevel: persona.autobook_risklevel,
      valid_from: persona.valid_from,
      valid_till: persona.valid_till,
    });
    setErrors({});
    setIsEditing(false);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDateForInput = (dateString: string) => {
    return new Date(dateString).toISOString().slice(0, 16);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{icon}</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">
                {persona.title}
              </h2>
              <p className="text-sm text-gray-500">
                {isEditing ? 'Edit Persona' : 'Persona Details'}
              </p>
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
        <div className="p-6 space-y-6">
          {errors.general && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {errors.general}
            </div>
          )}

          {/* Read-only fields */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Persona ID
              </label>
              <p className="text-sm font-mono text-gray-600 bg-gray-50 px-3 py-2 rounded border">
                {persona.persona_id}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Persona Title
              </label>
              <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                {persona.title}
              </p>
            </div>

            {/* Circle */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Circle <span className="text-red-500">*</span>
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={formData.circle}
                  onChange={(e) => setFormData({ ...formData, circle: e.target.value })}
                  placeholder="e.g., family, acme-corp, marketing-team"
                  className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                    errors.circle ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  {formData.circle}
                </p>
              )}
              {errors.circle && (
                <p className="text-xs text-red-600 mt-1">{errors.circle}</p>
              )}
              <p className="text-xs text-gray-500 mt-1">
                The community, business unit, or circle of trust for which this persona is valid
              </p>
            </div>
          </div>

          {/* Lifecycle */}
          <div className="space-y-4 pt-4 border-t">
            <h3 className="font-medium text-gray-900">Lifecycle</h3>

            {/* Status */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Status
              </label>
              {isEditing ? (
                <select
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="suspended">Suspended</option>
                  <option value="pending">Pending</option>
                  <option value="revoked">Revoked</option>
                </select>
              ) : (
                <span
                  className={`inline-block text-sm px-3 py-1 rounded-full ${
                    formData.status === 'active'
                      ? 'bg-green-100 text-green-800'
                      : formData.status === 'inactive'
                      ? 'bg-gray-100 text-gray-800'
                      : formData.status === 'suspended'
                      ? 'bg-orange-100 text-orange-800'
                      : 'bg-red-100 text-red-800'
                  }`}
                >
                  {formData.status.charAt(0).toUpperCase() + formData.status.slice(1)}
                </span>
              )}
            </div>

            {/* Valid From */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Valid From
              </label>
              {isEditing ? (
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={formatDateForInput(formData.valid_from).split('T')[0]}
                    onChange={(e) => {
                      const currentTime = formatDateForInput(formData.valid_from).split('T')[1];
                      const newDateTime = `${e.target.value}T${currentTime}`;
                      setFormData({
                        ...formData,
                        valid_from: new Date(newDateTime).toISOString(),
                      });
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
                  />
                  <input
                    type="time"
                    value={formatDateForInput(formData.valid_from).split('T')[1]}
                    onChange={(e) => {
                      const currentDate = formatDateForInput(formData.valid_from).split('T')[0];
                      const newDateTime = `${currentDate}T${e.target.value}`;
                      setFormData({
                        ...formData,
                        valid_from: new Date(newDateTime).toISOString(),
                      });
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
                  />
                </div>
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  {formatDate(formData.valid_from)}
                </p>
              )}
            </div>

            {/* Valid Until */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Valid Until
              </label>
              {isEditing ? (
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="date"
                    value={formatDateForInput(formData.valid_till).split('T')[0]}
                    onChange={(e) => {
                      const currentTime = formatDateForInput(formData.valid_till).split('T')[1];
                      const newDateTime = `${e.target.value}T${currentTime}`;
                      setFormData({
                        ...formData,
                        valid_till: new Date(newDateTime).toISOString(),
                      });
                    }}
                    className={`px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                      errors.valid_till ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                  <input
                    type="time"
                    value={formatDateForInput(formData.valid_till).split('T')[1]}
                    onChange={(e) => {
                      const currentDate = formatDateForInput(formData.valid_till).split('T')[0];
                      const newDateTime = `${currentDate}T${e.target.value}`;
                      setFormData({
                        ...formData,
                        valid_till: new Date(newDateTime).toISOString(),
                      });
                    }}
                    className={`px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                      errors.valid_till ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                </div>
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  {formatDate(formData.valid_till)}
                </p>
              )}
              {errors.valid_till && (
                <p className="text-xs text-red-600 mt-1">{errors.valid_till}</p>
              )}
            </div>
          </div>

          {/* Autobook Preferences */}
          <div className="space-y-4 pt-4 border-t">
            <h3 className="font-medium text-gray-900">Autobook Preferences</h3>

            {/* Consent */}
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.consent}
                  onChange={(e) =>
                    setFormData({ ...formData, consent: e.target.checked })
                  }
                  disabled={!isEditing}
                  className="w-4 h-4 text-nura-orange rounded focus:ring-2 focus:ring-nura-orange disabled:opacity-50"
                />
                <span className="text-sm font-medium text-gray-700">
                  Enable Automatic Booking
                </span>
              </label>
              <p className="text-xs text-gray-500 mt-1 ml-6">
                Allow AI agent to automatically book within set limits
              </p>
            </div>

            {/* Price Limit */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Price Limit (EUR)
              </label>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.autobook_price}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      autobook_price: parseFloat(e.target.value) || 0,
                    })
                  }
                  min="0"
                  step="100"
                  className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                    errors.autobook_price ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  €{formData.autobook_price}
                </p>
              )}
              {errors.autobook_price && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_price}</p>
              )}
            </div>

            {/* Lead Time */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Lead Time (Days)
              </label>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.autobook_leadtime}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      autobook_leadtime: parseInt(e.target.value) || 0,
                    })
                  }
                  min="0"
                  step="1"
                  className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                    errors.autobook_leadtime ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  {formData.autobook_leadtime} days
                </p>
              )}
              {errors.autobook_leadtime && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_leadtime}</p>
              )}
            </div>

            {/* Risk Level */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Risk Level (0-100)
              </label>
              {isEditing ? (
                <div>
                  <input
                    type="range"
                    value={formData.autobook_risklevel}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        autobook_risklevel: parseInt(e.target.value),
                      })
                    }
                    min="0"
                    max="100"
                    step="5"
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>Conservative (0)</span>
                    <span className="font-medium text-nura-orange">
                      {formData.autobook_risklevel}
                    </span>
                    <span>Aggressive (100)</span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-900 bg-gray-50 px-3 py-2 rounded border">
                  {formData.autobook_risklevel}
                </p>
              )}
              {errors.autobook_risklevel && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_risklevel}</p>
              )}
            </div>
          </div>

          {/* Metadata */}
          {(persona.created_at || persona.updated_at) && (
            <div className="pt-4 border-t text-xs text-gray-500 space-y-1">
              {persona.created_at && (
                <p>Created: {formatDate(persona.created_at)}</p>
              )}
              {persona.updated_at && (
                <p>Last updated: {formatDate(persona.updated_at)}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t bg-gray-50">
          {isEditing ? (
            <>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 bg-nura-orange text-white rounded-lg hover:bg-opacity-90 disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Close
              </button>
              {onSave && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="px-4 py-2 bg-nura-orange text-white rounded-lg hover:bg-opacity-90"
                >
                  Edit Persona
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
