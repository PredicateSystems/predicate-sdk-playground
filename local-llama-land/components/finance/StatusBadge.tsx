interface StatusBadgeProps {
  status: string;
  variant?: 'reconciliation' | 'payment' | 'priority';
}

const RECONCILIATION_COLORS: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  reconciled: 'bg-green-500/20 text-green-300 border-green-500/30',
  needs_review: 'bg-red-500/20 text-red-300 border-red-500/30',
};

const PAYMENT_COLORS: Record<string, string> = {
  unpaid: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  scheduled: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  paid: 'bg-green-500/20 text-green-300 border-green-500/30',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-500/20 text-red-300 border-red-500/30',
  medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  low: 'bg-white/10 text-white/60 border-white/20',
};

export function StatusBadge({ status, variant = 'reconciliation' }: StatusBadgeProps) {
  const colorMap =
    variant === 'payment'
      ? PAYMENT_COLORS
      : variant === 'priority'
        ? PRIORITY_COLORS
        : RECONCILIATION_COLORS;

  const colors = colorMap[status] || 'bg-white/10 text-white/60 border-white/20';
  const displayText = status.replace(/_/g, ' ');

  return (
    <span
      className={`px-2 py-0.5 rounded text-xs border ${colors}`}
      data-testid={`status-badge-${variant}`}
      data-status={status}
    >
      {displayText}
    </span>
  );
}
