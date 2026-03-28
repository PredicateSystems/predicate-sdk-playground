'use client';

import { useState, useEffect } from 'react';

interface ReconciliationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  invoiceId: string;
  willSilentlyFail: boolean;
}

/**
 * ReconciliationModal - The key demo component for silent failure
 *
 * When willSilentlyFail is true:
 * - The modal appears and looks normal
 * - User clicks "Confirm Reconciliation"
 * - Shows "Processing..." briefly
 * - Modal closes (appears successful)
 * - BUT: onConfirm is never called, so status doesn't change
 *
 * This simulates real-world failures like:
 * - Stale session tokens
 * - Backend validation failures not surfaced to UI
 * - Race conditions where modal closes before commit
 * - Click handler attached to wrong element
 */
export function ReconciliationModal({
  isOpen,
  onClose,
  onConfirm,
  invoiceId,
  willSilentlyFail,
}: ReconciliationModalProps) {
  const [isProcessing, setIsProcessing] = useState(false);

  // Reset processing state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setIsProcessing(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    setIsProcessing(true);

    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 800));

    if (willSilentlyFail) {
      // SILENT FAILURE PATH:
      // - We show "Processing..."
      // - We close the modal (looks like success)
      // - We do NOT call onConfirm (status doesn't change)
      //
      // This is the key demo moment: "the agent clicked the button,
      // but the state never changed"
      setIsProcessing(false);
      onClose();
      // Note: onConfirm() is intentionally NOT called
    } else {
      // Normal success path
      setIsProcessing(false);
      onConfirm();
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      data-testid="reconciliation-modal"
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
        <h2 className="text-xl font-semibold mb-2">Confirm Reconciliation</h2>
        <p className="text-white/70 text-sm mb-4">
          You are about to mark invoice <strong>{invoiceId}</strong> as reconciled.
          This action will update the invoice status and notify the payment team.
        </p>

        {/* Hidden indicator for testing - shows if this will silently fail */}
        <div
          data-testid="silent-failure-indicator"
          data-will-fail={willSilentlyFail ? 'true' : 'false'}
          className="hidden"
        />

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="px-4 py-2 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50"
            data-testid="modal-cancel"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isProcessing}
            className="px-4 py-2 text-sm rounded bg-green-600 hover:bg-green-500 transition-colors disabled:opacity-50 min-w-[140px]"
            data-testid="modal-confirm"
          >
            {isProcessing ? (
              <span className="flex items-center justify-center gap-2">
                <span
                  className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"
                  data-testid="processing-spinner"
                />
                Processing...
              </span>
            ) : (
              'Confirm Reconciliation'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
