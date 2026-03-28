'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { getVendorById, formatCurrency } from '@/lib/finance-data';

export default function VendorDetailPage() {
  const params = useParams();
  const vendorId = params.id as string;
  const vendor = getVendorById(vendorId);

  if (!vendor) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-semibold">Vendor Not Found</h1>
          <Link href="/demo/finance" className="text-sm text-blue-400 hover:text-blue-300">
            ← Back to Finance
          </Link>
        </div>
        <p className="text-white/60">Vendor record {vendorId} does not exist.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="vendor-detail-page">
      {/* External Vendor Portal Header - Different styling to distinguish from ERP */}
      <div className="border-b-2 border-emerald-500/30 pb-4">
        <div className="flex items-center gap-2 text-xs text-emerald-400/70 mb-2">
          <span className="px-2 py-0.5 bg-emerald-500/20 rounded text-emerald-300">
            VENDOR PORTAL
          </span>
          <span>•</span>
          <span>External System</span>
          <span>•</span>
          <span>Invoice Records</span>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-emerald-100" data-testid="vendor-name">
              {vendor.vendorName}
            </h1>
            <p className="text-emerald-300/60 mt-1 text-sm" data-testid="vendor-legal-name">
              {vendor.vendorLegalName}
            </p>
          </div>
          <Link
            href={`/demo/finance/invoices/${vendor.invoiceNumber}`}
            className="text-sm text-emerald-400 hover:text-emerald-300"
          >
            ← Back to Invoice
          </Link>
        </div>
      </div>

      {/* Main Content - Styled differently from ERP */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Invoice Information from Vendor's Perspective */}
        <div className="p-5 rounded-lg border border-emerald-500/20 bg-emerald-900/10">
          <h2 className="text-sm font-medium text-emerald-400/80 uppercase tracking-wide mb-4">
            Invoice Record
          </h2>
          <div className="space-y-3">
            <VendorField
              label="Invoice Number"
              value={vendor.invoiceNumber}
              testId="vendor-field-invoice-number"
            />
            <VendorField
              label="Billed Amount"
              value={formatCurrency(vendor.billedAmount, vendor.currency)}
              testId="vendor-field-billed-amount"
            />
            <VendorField
              label="Currency"
              value={vendor.currency}
              testId="vendor-field-currency"
            />
            <VendorField
              label="Invoice Date"
              value={vendor.invoiceDate}
              testId="vendor-field-invoice-date"
            />
            <VendorField
              label="Payment State"
              value={
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    vendor.paymentState === 'Payment Scheduled'
                      ? 'bg-blue-500/20 text-blue-300'
                      : 'bg-yellow-500/20 text-yellow-300'
                  }`}
                >
                  {vendor.paymentState}
                </span>
              }
              testId="vendor-field-payment-state"
            />
          </div>
        </div>

        {/* Vendor Contact Information */}
        <div className="p-5 rounded-lg border border-emerald-500/20 bg-emerald-900/10">
          <h2 className="text-sm font-medium text-emerald-400/80 uppercase tracking-wide mb-4">
            Vendor Information
          </h2>
          <div className="space-y-3">
            <VendorField
              label="Vendor ID"
              value={vendor.id}
              testId="vendor-field-id"
            />
            <VendorField
              label="Display Name"
              value={vendor.vendorName}
              testId="vendor-field-display-name"
            />
            <VendorField
              label="Legal Name"
              value={vendor.vendorLegalName}
              testId="vendor-field-legal-name"
            />
            <VendorField
              label="Contact Email"
              value={vendor.contactEmail}
              testId="vendor-field-email"
            />
            <VendorField
              label="Address"
              value={vendor.address}
              testId="vendor-field-address"
            />
          </div>
        </div>
      </div>

      {/* Comparison Quick View */}
      <div className="p-5 rounded-lg border border-white/10 bg-white/5">
        <h2 className="text-sm font-medium text-white/70 uppercase tracking-wide mb-4">
          Cross-System Comparison Fields
        </h2>
        <p className="text-xs text-white/50 mb-4">
          These fields are used by the reconciliation agent to verify consistency between ERP and vendor records.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="comparison-table">
            <thead>
              <tr className="border-b border-white/20 text-left text-white/60">
                <th className="pb-2 pr-4 font-medium">Field</th>
                <th className="pb-2 pr-4 font-medium">Vendor Record Value</th>
                <th className="pb-2 font-medium">Verifiable Selector</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              <tr>
                <td className="py-2 pr-4 text-white/70">Invoice Number</td>
                <td className="py-2 pr-4" data-testid="compare-invoice-number">
                  {vendor.invoiceNumber}
                </td>
                <td className="py-2 font-mono text-xs text-white/40">
                  [data-testid="vendor-field-invoice-number"]
                </td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-white/70">Vendor Name</td>
                <td className="py-2 pr-4" data-testid="compare-vendor-name">
                  {vendor.vendorName}
                </td>
                <td className="py-2 font-mono text-xs text-white/40">
                  [data-testid="vendor-field-display-name"]
                </td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-white/70">Billed Amount</td>
                <td className="py-2 pr-4" data-testid="compare-billed-amount">
                  {formatCurrency(vendor.billedAmount, vendor.currency)}
                </td>
                <td className="py-2 font-mono text-xs text-white/40">
                  [data-testid="vendor-field-billed-amount"]
                </td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-white/70">Invoice Date</td>
                <td className="py-2 pr-4" data-testid="compare-invoice-date">
                  {vendor.invoiceDate}
                </td>
                <td className="py-2 font-mono text-xs text-white/40">
                  [data-testid="vendor-field-invoice-date"]
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// Vendor-specific field component with different styling
function VendorField({
  label,
  value,
  testId,
}: {
  label: string;
  value: React.ReactNode;
  testId?: string;
}) {
  return (
    <div className="flex justify-between py-1.5 border-b border-emerald-500/10" data-testid={testId}>
      <span className="text-emerald-300/60 text-sm">{label}</span>
      <span
        className="text-emerald-100 font-medium text-sm text-right"
        data-testid={testId ? `${testId}-value` : undefined}
      >
        {value}
      </span>
    </div>
  );
}
