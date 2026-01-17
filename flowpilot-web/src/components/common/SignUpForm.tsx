import { useState } from 'react';
import { useAuth } from '../../state/AuthContext';

const ALLOWED_PERSONAS = [
  'traveler',
  'ai-agent',
  'travel-agent',
  'office-manager',
  'booking-assistant',
] as const;

export interface PersonaAttributes {
  consent: boolean;
  autobook_price: number;
  autobook_leadtime: number;
  autobook_risklevel: number;
}

export function SignUpForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [persona, setPersona] = useState<string>('');
  const [consent, setConsent] = useState(false);
  const [autobookPrice, setAutobookPrice] = useState(1500);
  const [autobookLeadtime, setAutobookLeadtime] = useState(7);
  const [autobookRisklevel, setAutobookRisklevel] = useState(50);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { signUp } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    if (!persona) {
      setError('Please select a persona');
      return;
    }

    // Validate persona attributes
    if (autobookPrice < 0) {
      setError('Max price must be a positive number');
      return;
    }
    if (autobookLeadtime < 0) {
      setError('Min lead time must be a positive number');
      return;
    }
    if (autobookRisklevel < 0 || autobookRisklevel > 100) {
      setError('Max risk level must be between 0 and 100');
      return;
    }

    setLoading(true);

    try {
      const personaAttrs: PersonaAttributes = {
        consent,
        autobook_price: autobookPrice,
        autobook_leadtime: autobookLeadtime,
        autobook_risklevel: autobookRisklevel,
      };
      await signUp(email, password, persona, personaAttrs);
    } catch (err: any) {
      setError(err.message || 'Sign up failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="signup-email" className="block text-sm font-medium text-gray-700 mb-1">
          Email
        </label>
        <input
          id="signup-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
          placeholder="your@email.com"
        />
      </div>

      <div>
        <label htmlFor="signup-password" className="block text-sm font-medium text-gray-700 mb-1">
          Password
        </label>
        <input
          id="signup-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
          placeholder="••••••••"
        />
      </div>

      <div>
        <label htmlFor="confirm-password" className="block text-sm font-medium text-gray-700 mb-1">
          Confirm Password
        </label>
        <input
          id="confirm-password"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
          placeholder="••••••••"
        />
      </div>

      <div>
        <label htmlFor="persona" className="block text-sm font-medium text-gray-700 mb-1">
          Initial Persona *
        </label>
        <select
          id="persona"
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
        >
          <option value="">Select a persona...</option>
          {ALLOWED_PERSONAS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div className="border-t pt-4">
        <h3 className="text-sm font-medium text-gray-900 mb-3">Auto-booking Settings</h3>
        
        <div className="space-y-3">
          <div className="flex items-center">
            <input
              id="consent"
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="h-4 w-4 text-nura-orange focus:ring-nura-orange border-gray-300 rounded"
            />
            <label htmlFor="consent" className="ml-2 block text-sm text-gray-700">
              Enable auto-booking
            </label>
          </div>

          <div>
            <label htmlFor="autobook-price" className="block text-sm font-medium text-gray-700 mb-1">
              Max Price (EUR) *
            </label>
            <input
              id="autobook-price"
              type="number"
              min="0"
              value={autobookPrice}
              onChange={(e) => setAutobookPrice(Number(e.target.value))}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
            />
          </div>

          <div>
            <label htmlFor="autobook-leadtime" className="block text-sm font-medium text-gray-700 mb-1">
              Min Lead Time (days) *
            </label>
            <input
              id="autobook-leadtime"
              type="number"
              min="0"
              value={autobookLeadtime}
              onChange={(e) => setAutobookLeadtime(Number(e.target.value))}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
            />
          </div>

          <div>
            <label htmlFor="autobook-risklevel" className="block text-sm font-medium text-gray-700 mb-1">
              Max Risk Level (0-100) *
            </label>
            <input
              id="autobook-risklevel"
              type="number"
              min="0"
              max="100"
              value={autobookRisklevel}
              onChange={(e) => setAutobookRisklevel(Number(e.target.value))}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-nura-orange focus:border-transparent"
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full px-6 py-3 bg-nura-orange text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? 'Creating account...' : 'Sign Up'}
      </button>
    </form>
  );
}
