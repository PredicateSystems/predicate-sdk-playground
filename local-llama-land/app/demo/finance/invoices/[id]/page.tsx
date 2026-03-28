'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import {
  StatusBadge,
  FieldRow,
  ActivityPanel,
  ReconciliationModal,
  ReleasePaymentModal,
  AddNoteModal,
} from '@/components/finance';
import { getInvoiceById, formatCurrency, type ActivityNote } from '@/lib/finance-data';

// High-value threshold for payment policy
const PAYMENT_THRESHOLD = 10000;

export default function InvoiceDetailPage() {
  const params = useParams();
  const invoiceId = params.id as string;
  const invoice = getInvoiceById(invoiceId);

  // Local state for reconciliation status (allows UI updates without backend)
  const [reconciliationStatus, setReconciliationStatus] = useState(invoice?.status ?? 'pending');
  const [paymentStatus, setPaymentStatus] = useState(invoice?.paymentStatus ?? 'unpaid');
  const [localNotes, setLocalNotes] = useState<ActivityNote[]>(invoice?.notes ?? []);

  // Modal states
  const [isReconciliationModalOpen, setIsReconciliationModalOpen] = useState(false);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isAddNoteModalOpen, setIsAddNoteModalOpen] = useState(false);

  if (!invoice) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-semibold">Invoice Not Found</h1>
          <Link href="/demo/finance/queue" className="text-sm text-blue-400 hover:text-blue-300">
            ← Back to Queue
          </Link>
        </div>
        <p className="text-white/60">Invoice {invoiceId} does not exist.</p>
      </div>
    );
  }

  // Determine if this invoice will silently fail reconciliation
  const willSilentlyFail = invoice.mismatch;

  // Determine if this is a high-value invoice (policy will deny payment)
  const isHighValue = invoice.amount > PAYMENT_THRESHOLD;

  // Generate timestamp for notes
  const getTimestamp = () => new Date().toISOString().slice(0, 16).replace('T', ' ');

  const handleMarkReconciled = () => {
    setIsReconciliationModalOpen(true);
  };

  const handleConfirmReconciliation = () => {
    setReconciliationStatus('reconciled');
    setLocalNotes((prev) => [
      ...prev,
      {
        author: 'Agent',
        timestamp: getTimestamp(),
        text: 'Reconciliation completed successfully.',
      },
    ]);
  };

  const handleRouteToReview = () => {
    // This action always works - it's the "corrected bounded action" in the demo
    setReconciliationStatus('needs_review');
    setLocalNotes((prev) => [
      ...prev,
      {
        author: 'Agent',
        timestamp: getTimestamp(),
        text: 'Routed to review queue for manual inspection.',
      },
    ]);
  };

  const handleReleasePayment = () => {
    setIsPaymentModalOpen(true);
  };

  const handleAddNote = () => {
    setIsAddNoteModalOpen(true);
  };

  const handleNoteSubmit = (noteText: string) => {
    setLocalNotes((prev) => [
      ...prev,
      {
        author: 'Agent',
        timestamp: getTimestamp(),
        text: noteText,
      },
    ]);
  };

  // Count notes for display
  const noteCount = localNotes.length;

  return (
    <div className="space-y-6" data-testid="invoice-detail-page">
      {/* ERP System Header */}
      <div className="border-b border-white/20 pb-4">
        <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
          <span>ACME ERP</span>
          <span>•</span>
          <span>Accounts Payable</span>
          <span>•</span>
          <span>Invoice Management</span>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold" data-testid="invoice-number">
              {invoice.id}
            </h1>
            <p className="text-white/60 mt-1">
              <span data-testid="invoice-vendor">{invoice.vendor}</span>
            </p>
          </div>
          <Link href="/demo/finance/queue" className="text-sm text-blue-400 hover:text-blue-300">
            ← Back to Queue
          </Link>
        </div>
      </div>

      {/* Mismatch Warning */}
      {invoice.mismatch && (
        <div
          className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm"
          data-testid="mismatch-warning"
        >
          <strong>Mismatch Detected:</strong> {invoice.mismatchReason}
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Invoice Details - Primary Panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* Invoice Information */}
          <div className="p-5 rounded-lg border border-white/20 bg-white/5">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-4">
              Invoice Details
            </h2>
            <div className="space-y-1">
              <FieldRow
                label="Invoice Number"
                value={invoice.id}
                testId="field-invoice-number"
              />
              <FieldRow
                label="Vendor"
                value={
                  <Link
                    href={`/demo/finance/vendor/${invoice.vendorId}`}
                    className="text-blue-400 hover:text-blue-300"
                  >
                    {invoice.vendor}
                  </Link>
                }
                testId="field-vendor"
              />
              <FieldRow
                label="Amount"
                value={
                  <span className={isHighValue ? 'text-orange-400' : ''}>
                    {formatCurrency(invoice.amount, invoice.currency)}
                    {isHighValue && (
                      <span className="ml-2 text-xs text-orange-400" data-testid="high-value-flag">
                        (High Value)
                      </span>
                    )}
                  </span>
                }
                testId="field-amount"
              />
              <FieldRow
                label="Currency"
                value={invoice.currency}
                testId="field-currency"
              />
              <FieldRow
                label="Invoice Date"
                value={invoice.invoiceDate}
                testId="field-invoice-date"
              />
              <FieldRow
                label="Due Date"
                value={invoice.dueDate}
                testId="field-due-date"
              />
              <FieldRow
                label="PO Reference"
                value={invoice.poReference}
                testId="field-po-reference"
              />
            </div>
          </div>

          {/* Status Panel */}
          <div className="p-5 rounded-lg border border-white/20 bg-white/5">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-4">
              Status
            </h2>
            <div className="space-y-1">
              <FieldRow
                label="Reconciliation Status"
                value={<StatusBadge status={reconciliationStatus} variant="reconciliation" />}
                testId="field-reconciliation-status"
              />
              <FieldRow
                label="Payment Status"
                value={<StatusBadge status={paymentStatus} variant="payment" />}
                testId="field-payment-status"
              />
              <FieldRow
                label="Priority"
                value={<StatusBadge status={invoice.priority} variant="priority" />}
                testId="field-priority"
              />
            </div>
          </div>

          {/* Activity / Notes */}
          <div className="p-5 rounded-lg border border-white/20 bg-white/5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-white/70 uppercase tracking-wide">
                Activity
              </h3>
              <span
                className="text-xs text-white/50 bg-white/10 px-2 py-0.5 rounded"
                data-testid="note-count"
              >
                {noteCount} {noteCount === 1 ? 'note' : 'notes'}
              </span>
            </div>
            <ActivityPanel notes={localNotes} title="" />
          </div>
        </div>

        {/* Actions Sidebar */}
        <div className="space-y-4">
          <div className="p-5 rounded-lg border border-white/20 bg-white/5">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-4">
              Actions
            </h2>
            <div className="space-y-2">
              <button
                onClick={handleMarkReconciled}
                className="w-full px-4 py-2 text-sm rounded bg-green-600 hover:bg-green-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="action-mark-reconciled"
                disabled={reconciliationStatus === 'reconciled'}
              >
                Mark Reconciled
              </button>
              <button
                onClick={handleRouteToReview}
                className="w-full px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="action-route-to-review"
                disabled={reconciliationStatus === 'needs_review'}
              >
                Route To Review
              </button>
              <button
                onClick={handleReleasePayment}
                className="w-full px-4 py-2 text-sm rounded bg-orange-600 hover:bg-orange-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="action-release-payment"
                disabled={paymentStatus !== 'unpaid'}
              >
                Release Payment
                {isHighValue && (
                  <span className="ml-1 text-xs opacity-70">(Requires Approval)</span>
                )}
              </button>
              <button
                onClick={handleAddNote}
                className="w-full px-4 py-2 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors"
                data-testid="action-add-note"
              >
                Add Note
              </button>
            </div>
          </div>

          {/* Quick Links */}
          <div className="p-5 rounded-lg border border-white/20 bg-white/5">
            <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-4">
              Related
            </h2>
            <div className="space-y-2 text-sm">
              <Link
                href={`/demo/finance/vendor/${invoice.vendorId}`}
                className="block text-blue-400 hover:text-blue-300"
                data-testid="link-vendor-portal"
              >
                View Vendor Record →
              </Link>
              <Link
                href="/demo/finance/review"
                className="block text-blue-400 hover:text-blue-300"
              >
                Review Queue →
              </Link>
            </div>
          </div>

          {/* Debug Info - Hidden but testable */}
          <div
            className="hidden"
            data-testid="debug-info"
            data-current-status={reconciliationStatus}
            data-payment-status={paymentStatus}
            data-will-silently-fail={willSilentlyFail ? 'true' : 'false'}
            data-is-high-value={isHighValue ? 'true' : 'false'}
            data-invoice-id={invoice.id}
            data-note-count={noteCount}
          />
        </div>
      </div>

      {/* Modals */}
      <ReconciliationModal
        isOpen={isReconciliationModalOpen}
        onClose={() => setIsReconciliationModalOpen(false)}
        onConfirm={handleConfirmReconciliation}
        invoiceId={invoice.id}
        willSilentlyFail={willSilentlyFail}
      />

      <ReleasePaymentModal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        invoiceId={invoice.id}
        amount={invoice.amount}
        currency={invoice.currency}
        isHighValue={isHighValue}
      />

      <AddNoteModal
        isOpen={isAddNoteModalOpen}
        onClose={() => setIsAddNoteModalOpen(false)}
        onAddNote={handleNoteSubmit}
        invoiceId={invoice.id}
      />
    </div>
  );
}
