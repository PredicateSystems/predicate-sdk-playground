'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { StatusBadge, FieldRow, ActivityPanel } from '@/components/finance';
import { getInvoiceById, formatCurrency } from '@/lib/finance-data';

export default function InvoiceDetailPage() {
  const params = useParams();
  const invoiceId = params.id as string;
  const invoice = getInvoiceById(invoiceId);

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
                value={formatCurrency(invoice.amount, invoice.currency)}
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
                value={<StatusBadge status={invoice.status} variant="reconciliation" />}
                testId="field-reconciliation-status"
              />
              <FieldRow
                label="Payment Status"
                value={<StatusBadge status={invoice.paymentStatus} variant="payment" />}
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
            <ActivityPanel notes={invoice.notes} />
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
                className="w-full px-4 py-2 text-sm rounded bg-green-600 hover:bg-green-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="action-mark-reconciled"
                disabled={invoice.status === 'reconciled'}
              >
                Mark Reconciled
              </button>
              <button
                className="w-full px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 transition-colors"
                data-testid="action-route-to-review"
              >
                Route To Review
              </button>
              <button
                className="w-full px-4 py-2 text-sm rounded bg-orange-600 hover:bg-orange-500 transition-colors"
                data-testid="action-release-payment"
              >
                Release Payment
              </button>
              <button
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
        </div>
      </div>
    </div>
  );
}
