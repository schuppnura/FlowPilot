interface StatusBadgeProps {
  status: string;
  decision?: string;
}

export function StatusBadge({ status, decision }: StatusBadgeProps) {
  const getStatusColor = (status: string, decision?: string) => {
    const statusLower = status.toLowerCase();
    const decisionLower = decision?.toLowerCase();

    if (statusLower === 'error') {
      return 'bg-red-100 text-red-800 border-red-200';
    }
    if (decisionLower === 'deny') {
      return 'bg-orange-100 text-orange-800 border-orange-200';
    }
    if (decisionLower === 'allow' || statusLower === 'executed' || statusLower === 'completed') {
      return 'bg-green-100 text-green-800 border-green-200';
    }
    if (statusLower === 'planned') {
      return 'bg-blue-100 text-blue-800 border-blue-200';
    }
    return 'bg-gray-100 text-gray-800 border-gray-200';
  };

  const getStatusText = (status: string, decision?: string) => {
    const statusLower = status.toLowerCase();
    const decisionLower = decision?.toLowerCase();

    if (statusLower === 'error') {
      return 'ERROR';
    }
    if (decisionLower === 'deny') {
      return 'NO AUTOBOOKING';
    }
    if (decisionLower === 'allow') {
      return 'AUTOBOOK READY';
    }
    return status.toUpperCase();
  };

  const getStatusIcon = (status: string, decision?: string) => {
    const statusLower = status.toLowerCase();
    const decisionLower = decision?.toLowerCase();

    if (statusLower === 'error') {
      return '❌';
    }
    if (decisionLower === 'deny') {
      return '🛡️';
    }
    if (decisionLower === 'allow') {
      return '✅';
    }
    return '❓';
  };

  return (
    <span
      className={`px-3 py-1.5 text-xs font-semibold rounded-lg border flex items-center gap-1 ${getStatusColor(
        status,
        decision
      )}`}
    >
      <span className="text-xs">{getStatusIcon(status, decision)}</span>
      {getStatusText(status, decision)}
    </span>
  );
}
