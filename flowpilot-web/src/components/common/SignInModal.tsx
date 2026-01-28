import { useState, useEffect } from 'react';
import { SignInForm } from './SignInForm';
import { SignUpForm } from './SignUpForm';

interface SignInModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SignInModal({ isOpen, onClose }: SignInModalProps) {
  const [isSignUp, setIsSignUp] = useState(false);

  // Reset to sign-in mode when modal opens
  useEffect(() => {
    if (isOpen) {
      setIsSignUp(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black bg-opacity-50"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4 z-10">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="Close"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

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
    </div>
  );
}
