import { useEffect, useState } from 'react';

interface ColdStartNoticeProps {
  isLoading: boolean;
  delayThresholdMs?: number; // Show notice after this delay
  message?: string;
}

export function ColdStartNotice({
  isLoading,
  delayThresholdMs = 3000, // Default: show after 3 seconds
  message = 'The services are waking up from hibernation. This may take 10-30 seconds on first use. Please wait...',
}: ColdStartNoticeProps) {
  const [showNotice, setShowNotice] = useState(false);

  useEffect(() => {
    let timer: NodeJS.Timeout;

    if (isLoading) {
      // Set timer to show notice after threshold
      timer = setTimeout(() => {
        setShowNotice(true);
      }, delayThresholdMs);
    } else {
      // Hide notice when loading completes
      setShowNotice(false);
    }

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isLoading, delayThresholdMs]);

  if (!showNotice) {
    return null;
  }

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className="h-5 w-5 text-blue-600 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-blue-800">Just a moment...</p>
          <p className="text-sm text-blue-700 mt-1">{message}</p>
        </div>
      </div>
    </div>
  );
}

// Hook to automatically detect slow requests
export function useColdStartDetection(isLoading: boolean, thresholdMs: number = 3000) {
  const [showColdStartNotice, setShowColdStartNotice] = useState(false);

  useEffect(() => {
    let timer: NodeJS.Timeout;

    if (isLoading) {
      timer = setTimeout(() => {
        setShowColdStartNotice(true);
      }, thresholdMs);
    } else {
      setShowColdStartNotice(false);
    }

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isLoading, thresholdMs]);

  return showColdStartNotice;
}
