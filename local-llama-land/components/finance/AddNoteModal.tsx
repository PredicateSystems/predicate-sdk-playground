'use client';

import { useState, useEffect } from 'react';

interface AddNoteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddNote: (noteText: string) => void;
  invoiceId: string;
}

/**
 * AddNoteModal - Safe bounded action that always succeeds
 *
 * Adding a note is a low-risk action that the policy always allows.
 * This is the "corrected bounded action" when other actions are denied.
 */
export function AddNoteModal({
  isOpen,
  onClose,
  onAddNote,
  invoiceId,
}: AddNoteModalProps) {
  const [noteText, setNoteText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setNoteText('');
      setIsSubmitting(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!noteText.trim()) return;

    setIsSubmitting(true);

    // Brief delay to feel realistic
    await new Promise((resolve) => setTimeout(resolve, 300));

    onAddNote(noteText.trim());
    setIsSubmitting(false);
    onClose();
  };

  // Predefined quick notes for the demo
  const quickNotes = [
    'Requesting manager approval for payment release.',
    'Vendor contacted to verify invoice details.',
    'PO mismatch under investigation.',
    'Escalating to finance team for review.',
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      data-testid="add-note-modal"
      data-modal-open="true"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        data-testid="modal-backdrop"
      />

      {/* Modal Content */}
      <div
        className="relative z-10 w-full max-w-md p-6 rounded-lg border border-white/20 bg-zinc-900 shadow-xl"
        data-testid="modal-content"
      >
        <h2 className="text-xl font-semibold mb-2">Add Note</h2>
        <p className="text-white/60 text-sm mb-4">
          Add a note to invoice <strong>{invoiceId}</strong>
        </p>

        {/* Quick note buttons */}
        <div className="mb-4">
          <p className="text-xs text-white/50 mb-2">Quick notes:</p>
          <div className="flex flex-wrap gap-2">
            {quickNotes.map((note, idx) => (
              <button
                key={idx}
                onClick={() => setNoteText(note)}
                className="px-2 py-1 text-xs rounded bg-white/10 hover:bg-white/20 transition-colors text-white/70"
                data-testid={`quick-note-${idx}`}
              >
                {note.slice(0, 30)}...
              </button>
            ))}
          </div>
        </div>

        {/* Text area */}
        <textarea
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          placeholder="Enter your note..."
          className="w-full h-24 p-3 rounded bg-white/5 border border-white/20 text-white placeholder-white/40 text-sm resize-none focus:outline-none focus:border-blue-500"
          data-testid="note-textarea"
        />

        <div className="flex gap-3 justify-end mt-4">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50"
            data-testid="modal-cancel"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !noteText.trim()}
            className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 transition-colors disabled:opacity-50"
            data-testid="modal-submit-note"
          >
            {isSubmitting ? 'Adding...' : 'Add Note'}
          </button>
        </div>
      </div>
    </div>
  );
}
