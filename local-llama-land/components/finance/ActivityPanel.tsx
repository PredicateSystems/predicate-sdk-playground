import type { ActivityNote } from '@/lib/finance-data';

interface ActivityPanelProps {
  notes: ActivityNote[];
  title?: string;
}

export function ActivityPanel({ notes, title = 'Activity' }: ActivityPanelProps) {
  return (
    <div className="space-y-3" data-testid="activity-panel">
      <h3 className="text-sm font-medium text-white/70 uppercase tracking-wide">{title}</h3>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {notes.length === 0 ? (
          <p className="text-sm text-white/40">No activity recorded.</p>
        ) : (
          notes.map((note, idx) => (
            <div
              key={idx}
              className="text-sm border-l-2 border-white/20 pl-3 py-1"
              data-testid={`activity-note-${idx}`}
            >
              <div className="text-white/50 text-xs">
                <span data-testid={`activity-author-${idx}`}>{note.author}</span>
                {' · '}
                <span data-testid={`activity-timestamp-${idx}`}>{note.timestamp}</span>
              </div>
              <div className="text-white/80" data-testid={`activity-text-${idx}`}>
                {note.text}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
