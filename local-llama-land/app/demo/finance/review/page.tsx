'use client';

import Link from 'next/link';
import { REVIEW_ITEMS, formatCurrency } from '@/lib/finance-data';

const REASON_COLORS: Record<string, string> = {
  amount_mismatch: 'bg-orange-500/20 text-orange-300',
  vendor_name_mismatch: 'bg-purple-500/20 text-purple-300',
  missing_po: 'bg-red-500/20 text-red-300',
  duplicate: 'bg-yellow-500/20 text-yellow-300',
};

export default function ReviewQueuePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Review Queue</h1>
          <p className="text-white/70 mt-1">
            {REVIEW_ITEMS.length} cases awaiting manual review
          </p>
        </div>
        <Link
          href="/demo/finance"
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          ← Back to Finance
        </Link>
      </div>

      {/* Review cards */}
      <div className="space-y-4" data-testid="review-queue">
        {REVIEW_ITEMS.map((item) => (
          <div
            key={item.id}
            className="p-5 rounded-lg border border-white/20 bg-white/5 space-y-4"
            data-testid={`review-item-${item.id}`}
          >
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <span className="font-medium">{item.id}</span>
                  <Link
                    href={`/demo/finance/invoices/${item.invoiceId}`}
                    className="text-blue-400 hover:text-blue-300 text-sm"
                  >
                    {item.invoiceId}
                  </Link>
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${REASON_COLORS[item.reasonCode] || 'bg-white/20 text-white/70'}`}
                  >
                    {item.reasonCode.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="text-white/60 text-sm mt-1">
                  {item.vendor} · {formatCurrency(item.amount)}
                </div>
              </div>
              <div className="text-right text-sm text-white/50">
                <div>Assigned: {item.assignedTo}</div>
                <div>{item.createdAt}</div>
              </div>
            </div>

            {/* Reason */}
            <div className="text-sm text-white/80 p-3 rounded bg-white/5">
              {item.reasonText}
            </div>

            {/* Activity / Notes */}
            <div>
              <h4 className="text-xs font-medium text-white/50 uppercase tracking-wide mb-2">
                Activity
              </h4>
              <div className="space-y-2">
                {item.notes.map((note, idx) => (
                  <div
                    key={idx}
                    className="text-sm border-l-2 border-white/20 pl-3 py-1"
                  >
                    <div className="text-white/50 text-xs">
                      {note.author} · {note.timestamp}
                    </div>
                    <div className="text-white/80">{note.text}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <button
                className="px-3 py-1.5 text-sm rounded bg-green-600 hover:bg-green-500 transition-colors"
                data-testid={`resolve-${item.id}`}
              >
                Resolve
              </button>
              <button
                className="px-3 py-1.5 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors"
                data-testid={`escalate-${item.id}`}
              >
                Escalate
              </button>
              <button
                className="px-3 py-1.5 text-sm rounded bg-white/10 hover:bg-white/20 transition-colors"
              >
                Add Note
              </button>
            </div>
          </div>
        ))}
      </div>

      {REVIEW_ITEMS.length === 0 && (
        <div className="text-center py-8 text-white/50">
          No cases in review queue.
        </div>
      )}
    </div>
  );
}
