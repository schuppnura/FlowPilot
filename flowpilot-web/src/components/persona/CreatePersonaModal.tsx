import { useState } from 'react';

interface CreatePersonaData {
  title: string;
  scope: string[];
  consent: boolean;
  autobook_price: number;
  autobook_leadtime: number;
  autobook_risklevel: number;
  valid_from: string;
  valid_till: string;
}

interface CreatePersonaModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (personaData: CreatePersonaData) => Promise<void>;
  existingTitles: string[];
  currentPersonaCount: number;
}

// Persona icons mapping
const PERSONA_ICONS: Record<string, string> = {
  'visitor': '👁️',
  'traveler': '🛡️',
  'business-traveler': '💼',
  'travel-agent': '👔',
  'office-manager': '📊',
  'booking-assistant': '📋',
  'user-admin': '👤',
};

const PERSONA_TITLES = [
  'visitor',
  'traveler',
  'business-traveler',
  'travel-agent',
  'office-manager',
  'booking-assistant',
  'user-admin',
];

// Sensible defaults
const DEFAULT_CONSENT = false;
const DEFAULT_PRICE = 1500;
const DEFAULT_LEADTIME = 7;
const DEFAULT_RISKLEVEL = 50;

export function CreatePersonaModal({
  isOpen,
  onClose,
  onCreate,
  existingTitles,
  currentPersonaCount,
}: CreatePersonaModalProps) {
  const now = new Date();
  const oneYearFromNow = new Date(now.getFullYear() + 1, now.getMonth(), now.getDate());

  const [formData, setFormData] = useState<CreatePersonaData>({
    title: '',
    scope: ['read', 'execute'],
    consent: DEFAULT_CONSENT,
    autobook_price: DEFAULT_PRICE,
    autobook_leadtime: DEFAULT_LEADTIME,
    autobook_risklevel: DEFAULT_RISKLEVEL,
    valid_from: now.toISOString(),
    valid_till: oneYearFromNow.toISOString(),
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isCreating, setIsCreating] = useState(false);

  if (!isOpen) return null;

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Check max personas limit
    if (currentPersonaCount >= 5) {
      newErrors.general = 'Maximum 5 personas per user';
      setErrors(newErrors);
      return false;
    }

    // Title required
    if (!formData.title) {
      newErrors.title = 'Persona title is required';
    }

    // Check duplicate title
    if (formData.title && existingTitles.includes(formData.title)) {
      newErrors.title = 'Cannot create duplicate persona title';
    }

    // Price validation
    if (formData.autobook_price <= 0) {
      newErrors.autobook_price = 'Price must be a positive number';
    }

    // Lead time validation
    if (formData.autobook_leadtime <= 0) {
      newErrors.autobook_leadtime = 'Lead time must be a positive number of days';
    }

    // Risk level validation
    if (formData.autobook_risklevel < 0 || formData.autobook_risklevel > 100) {
      newErrors.autobook_risklevel = 'Risk level must be between 0 and 100';
    }

    // Date validation
    const validFrom = new Date(formData.valid_from);
    const validTill = new Date(formData.valid_till);
    if (validTill <= validFrom) {
      newErrors.valid_till = 'Valid until must be after valid from';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleCreate = async () => {
    if (!validateForm()) return;

    setIsCreating(true);
    try {
      await onCreate(formData);
      // Reset form
      setFormData({
        title: '',
        scope: ['read', 'execute'],
        consent: DEFAULT_CONSENT,
        autobook_price: DEFAULT_PRICE,
        autobook_leadtime: DEFAULT_LEADTIME,
        autobook_risklevel: DEFAULT_RISKLEVEL,
        valid_from: now.toISOString(),
        valid_till: oneYearFromNow.toISOString(),
      });
      setErrors({});
      onClose();
    } catch (error: any) {
      setErrors({ general: error.message || 'Failed to create persona' });
    } finally {
      setIsCreating(false);
    }
  };

  const handleCancel = () => {
    // Reset form
    setFormData({
      title: '',
      scope: ['read', 'execute'],
      consent: DEFAULT_CONSENT,
      autobook_price: DEFAULT_PRICE,
      autobook_leadtime: DEFAULT_LEADTIME,
      autobook_risklevel: DEFAULT_RISKLEVEL,
      valid_from: now.toISOString(),
      valid_till: oneYearFromNow.toISOString(),
    });
    setErrors({});
    onClose();
  };

  const formatDateForInput = (dateString: string) => {
    return new Date(dateString).toISOString().slice(0, 16);
  };

  const availableTitles = PERSONA_TITLES.filter(title => !existingTitles.includes(title));
  const selectedIcon = formData.title ? PERSONA_ICONS[formData.title] || '🎭' : '🎭';

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{selectedIcon}</span>
            <div>
              <h2 className="text-2xl font-medium text-gray-900">
                Create New Persona
              </h2>
              <p className="text-sm text-gray-500">
                {currentPersonaCount}/5 personas created
              </p>
            </div>
          </div>
          <button
            onClick={handleCancel}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Demo Notice */}
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start gap-3">
              <span className="text-blue-600 text-xl">ℹ️</span>
              <div className="flex-1">
                <h4 className="text-sm font-medium text-blue-900 mb-1">Demo Mode</h4>
                <p className="text-sm text-blue-800">
                  For demonstration purposes, you can freely create and assign personas to yourself. 
                  In a production environment, personas would be provisioned through a formal onboarding 
                  process with proper authorization and verification.
                </p>
              </div>
            </div>
          </div>

          {errors.general && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {errors.general}
            </div>
          )}

          {/* Persona Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Persona Title <span className="text-red-500">*</span>
            </label>
            <select
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                errors.title ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Select a persona type...</option>
              {availableTitles.map((title) => (
                <option key={title} value={title}>
                  {PERSONA_ICONS[title] || '🎭'} {title}
                </option>
              ))}
            </select>
            {errors.title && (
              <p className="text-xs text-red-600 mt-1">{errors.title}</p>
            )}
            {availableTitles.length === 0 && (
              <p className="text-xs text-yellow-600 mt-1">
                All standard persona types are already in use. Consider deactivating an existing persona.
              </p>
            )}
            <p className="text-xs text-gray-500 mt-2">
              Permissions are determined by the selected persona type
            </p>
          </div>

          {/* Persona Lifecycle */}
          <div className="space-y-4 pt-4 border-t">
            <h3 className="font-medium text-gray-900">Persona Lifecycle</h3>
            
            {/* Valid From */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Valid From
              </label>
              <input
                type="datetime-local"
                value={formatDateForInput(formData.valid_from)}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    valid_from: new Date(e.target.value).toISOString(),
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">When this persona becomes active (default: now)</p>
            </div>

            {/* Valid Until */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Valid Until
              </label>
              <input
                type="datetime-local"
                value={formatDateForInput(formData.valid_till)}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    valid_till: new Date(e.target.value).toISOString(),
                  })
                }
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent ${
                  errors.valid_till ? 'border-red-500' : 'border-gray-300'
                }`}
              />
              <p className="text-xs text-gray-500 mt-1">When this persona expires (default: 1 year from now)</p>
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
                  className="w-4 h-4 text-nura-orange rounded focus:ring-2 focus:ring-nura-orange"
                />
                <span className="text-sm font-medium text-gray-700">
                  Enable Automatic Booking
                </span>
              </label>
              <p className="text-xs text-gray-500 mt-1 ml-6">
                Allow AI agent to automatically book within set limits (default: disabled)
              </p>
            </div>

            {/* Price Limit */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Price Limit (EUR)
              </label>
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
              <p className="text-xs text-gray-500 mt-1">Default: €{DEFAULT_PRICE}</p>
              {errors.autobook_price && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_price}</p>
              )}
            </div>

            {/* Lead Time */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Lead Time (Days)
              </label>
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
              <p className="text-xs text-gray-500 mt-1">Default: {DEFAULT_LEADTIME} days</p>
              {errors.autobook_leadtime && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_leadtime}</p>
              )}
            </div>

            {/* Risk Level */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Risk Level (0-100)
              </label>
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
                  {formData.autobook_risklevel} (Default: {DEFAULT_RISKLEVEL})
                </span>
                <span>Aggressive (100)</span>
              </div>
              {errors.autobook_risklevel && (
                <p className="text-xs text-red-600 mt-1">{errors.autobook_risklevel}</p>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t bg-gray-50">
          <button
            onClick={handleCancel}
            disabled={isCreating}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={isCreating || currentPersonaCount >= 5 || !formData.title}
            className="px-4 py-2 bg-nura-orange text-white rounded-lg hover:bg-opacity-90 disabled:opacity-50"
          >
            {isCreating ? 'Creating...' : 'Create Persona'}
          </button>
        </div>
      </div>
    </div>
  );
}
