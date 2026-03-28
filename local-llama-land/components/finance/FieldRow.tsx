interface FieldRowProps {
  label: string;
  value: React.ReactNode;
  testId?: string;
  highlight?: boolean;
}

export function FieldRow({ label, value, testId, highlight = false }: FieldRowProps) {
  return (
    <div
      className={`flex justify-between py-2 border-b border-white/10 ${highlight ? 'bg-yellow-500/10' : ''}`}
      data-testid={testId}
    >
      <span className="text-white/60 text-sm">{label}</span>
      <span className="text-white font-medium text-sm" data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </span>
    </div>
  );
}
