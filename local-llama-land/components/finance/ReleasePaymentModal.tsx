'use client';

import { useState, useEffect } from 'react';
import { formatCurrency } from '@/lib/finance-data';

interface ReleasePaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  invoiceId: string;
  amount: number;
  currency: string;
  isHighValue: boolean;
}

/**
 * ReleasePaymentModal - The risky action that policy will deny
 *
 * This modal represents the high-risk action in the demo.
 * In the full demo with sidecar integration, attempting this action
 * on a high-value invoice will be denied by policy BEFORE execution.
 *
 * For now, it simulates the UI surface that would be policy-blocked.
 * High-value invoices (amount > $10,000) are flagged as requiring approval.
 */
export function ReleasePaymentModal({
  isOpen,
  onClose,
  invoiceId,
  amount,
  currency,
  isHighValue,
}: ReleasePaymentModalProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [showDenied, setShowDenied] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setIsProcessing(false);
      setShowDenied(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleReleasePayment = async () => {
    setIsProcessing(true);

    // Simulate policy check delay
    await new Promise((resolve) => setTimeout(resolve, 600));

    if (isHighValue) {
      // POLICY DENIAL:
      // High-value payments are blocked - this is what the sidecar would do
      setIsProcessing(false);
      setShowDenied(true);
    } else {
      // Low-value payments would succeed (not in this demo scope)
      setIsProcessing(false);
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      data-testid="release-payment-modal"
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
        {showDenied ? (
          // Policy Denial View
          <div data-testid="payment-denied-view">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
                <span className="text-red-400 text-xl">✕</span>
              </div>
              <h2 className="text-xl font-semibold text-red-400">Action Denied</h2>
            </div>

            <div
              className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 mb-4"
              data-testid="policy-denial-message"
            >
              <p className="text-red-300 text-sm font-medium mb-2">
                Policy Violation: Payment Release Blocked
              </p>
              <p className="text-red-200/70 text-sm">
                Invoice <strong>{invoiceId}</strong> exceeds the payment threshold of $10,000.00.
                This action requires explicit approval from a finance manager.
              </p>
            </div>

            <div className="text-sm text-white/60 mb-4">
              <p className="mb-2">Suggested alternatives:</p>
              <ul className="list-disc list-inside space-y-1 text-white/50">
                <li>Route to review for manager approval</li>
                <li>Add a note requesting payment authorization</li>
                <li>Contact the AP manager directly</li>
              </ul>
            </div>

            {/* Hidden indicator for testing */}
            <div
              className="hidden"
              data-testid="denial-reason"
              data-reason="exceeds_threshold"
              data-threshold="10000"
              data-invoice-amount={amount}
            />

            <div className="flex justify-end">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors"
                data-testid="modal-dismiss"
              >
                Dismiss
              </button>
            </div>
          </div>
        ) : (
          // Confirmation View
          <div data-testid="payment-confirm-view">
            <h2 className="text-xl font-semibold mb-2">Release Payment</h2>

            <div className="p-4 rounded-lg bg-orange-500/10 border border-orange-500/30 mb-4">
              <p className="text-orange-300 text-sm">
                <strong>Warning:</strong> You are about to release payment for this invoice.
                This action cannot be undone.
              </p>
            </div>

            <div className="space-y-2 mb-4 text-sm">
              <div className="flex justify-between">
                <span className="text-white/60">Invoice:</span>
                <span className="font-medium">{invoiceId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-white/60">Amount:</span>
                <span className="font-medium font-mono">{formatCurrency(amount, currency)}</span>
              </div>
              {isHighValue && (
                <div className="flex justify-between text-orange-400">
                  <span>Risk Level:</span>
                  <span className="font-medium" data-testid="high-value-indicator">
                    High Value
                  </span>
                </div>
              )}
            </div>

            {/* Hidden indicator for testing */}
            <div
              className="hidden"
              data-testid="payment-info"
              data-is-high-value={isHighValue ? 'true' : 'false'}
              data-amount={amount}
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
                onClick={handleReleasePayment}
                disabled={isProcessing}
                className="px-4 py-2 text-sm rounded bg-orange-600 hover:bg-orange-500 transition-colors disabled:opacity-50 min-w-[140px]"
                data-testid="modal-confirm-payment"
              >
                {isProcessing ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Checking...
                  </span>
                ) : (
                  'Release Payment'
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
