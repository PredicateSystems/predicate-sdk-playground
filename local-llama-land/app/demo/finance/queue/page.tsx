'use client';

import Link from 'next/link';
import { useState } from 'react';
import { INVOICES, formatCurrency } from '@/lib/finance-data';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-300',
  reconciled: 'bg-green-500/20 text-green-300',
  needs_review: 'bg-red-500/20 text-red-300',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'text-red-400',
  medium: 'text-yellow-400',
  low: 'text-white/50',
};

export default function InvoiceQueuePage() {
  const [filter, setFilter] = useState<string>('all');

  const filteredInvoices =
    filter === 'all' ? INVOICES : INVOICES.filter((inv) => inv.status === filter);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Invoice Queue</h1>
          <p className="text-white/70 mt-1">
            {INVOICES.length} invoices · {INVOICES.filter((i) => i.status === 'pending').length}{' '}
            pending
          </p>
        </div>
        <Link
          href="/demo/finance"
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          ← Back to Finance
        </Link>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {['all', 'pending', 'reconciled', 'needs_review'].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              filter === status
                ? 'bg-white/20 text-white'
                : 'bg-white/5 text-white/60 hover:bg-white/10'
            }`}
          >
            {status === 'all' ? 'All' : status.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Invoice table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="invoice-table">
          <thead>
            <tr className="border-b border-white/20 text-left text-white/60">
              <th className="pb-3 pr-4 font-medium">Invoice #</th>
              <th className="pb-3 pr-4 font-medium">Vendor</th>
              <th className="pb-3 pr-4 font-medium text-right">Amount</th>
              <th className="pb-3 pr-4 font-medium">Due Date</th>
              <th className="pb-3 pr-4 font-medium">Status</th>
              <th className="pb-3 pr-4 font-medium">Priority</th>
              <th className="pb-3 font-medium">PO Ref</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {filteredInvoices.map((invoice) => (
              <tr
                key={invoice.id}
                className="hover:bg-white/5 transition-colors"
                data-testid={`invoice-row-${invoice.id}`}
              >
                <td className="py-3 pr-4">
                  <Link
                    href={`/demo/finance/invoices/${invoice.id}`}
                    className="text-blue-400 hover:text-blue-300"
                  >
                    {invoice.id}
                  </Link>
                  {invoice.mismatch && (
                    <span className="ml-2 text-xs text-red-400" title="Field mismatch detected">
                      ⚠️
                    </span>
                  )}
                </td>
                <td className="py-3 pr-4">{invoice.vendor}</td>
                <td className="py-3 pr-4 text-right font-mono">
                  {formatCurrency(invoice.amount, invoice.currency)}
                </td>
                <td className="py-3 pr-4 text-white/70">{invoice.dueDate}</td>
                <td className="py-3 pr-4">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[invoice.status]}`}
                    data-testid={`status-${invoice.id}`}
                  >
                    {invoice.status.replace('_', ' ')}
                  </span>
                </td>
                <td className={`py-3 pr-4 ${PRIORITY_COLORS[invoice.priority]}`}>
                  {invoice.priority}
                </td>
                <td className="py-3 font-mono text-white/70">{invoice.poReference}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredInvoices.length === 0 && (
        <div className="text-center py-8 text-white/50">No invoices match the current filter.</div>
      )}
    </div>
  );
}
