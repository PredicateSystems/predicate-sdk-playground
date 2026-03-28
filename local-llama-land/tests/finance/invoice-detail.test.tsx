import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import InvoiceDetailPage from '../../app/demo/finance/invoices/[id]/page';

// Mock next/navigation - default to INV-2024-001
const mockUseParams = vi.fn();
vi.mock('next/navigation', () => ({
  useParams: () => mockUseParams(),
}));

describe('Invoice Detail Page - INV-2024-001', () => {
  beforeEach(() => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
  });

  it('renders the invoice number in the header', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('invoice-number')).toHaveTextContent('INV-2024-001');
  });

  it('renders the vendor name', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('invoice-vendor')).toHaveTextContent('Acme Corp');
  });

  it('displays all required invoice fields', () => {
    render(<InvoiceDetailPage />);

    // Invoice details
    expect(screen.getByTestId('field-invoice-number')).toBeInTheDocument();
    expect(screen.getByTestId('field-vendor')).toBeInTheDocument();
    expect(screen.getByTestId('field-amount')).toBeInTheDocument();
    expect(screen.getByTestId('field-due-date')).toBeInTheDocument();
    expect(screen.getByTestId('field-po-reference')).toBeInTheDocument();

    // Status fields
    expect(screen.getByTestId('field-reconciliation-status')).toBeInTheDocument();
    expect(screen.getByTestId('field-payment-status')).toBeInTheDocument();
  });

  it('displays the correct amount value', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('field-amount-value')).toHaveTextContent('$12,500.00');
  });

  it('displays the PO reference', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('field-po-reference-value')).toHaveTextContent('PO-8821');
  });

  it('renders action buttons', () => {
    render(<InvoiceDetailPage />);

    expect(screen.getByTestId('action-mark-reconciled')).toBeInTheDocument();
    expect(screen.getByTestId('action-route-to-review')).toBeInTheDocument();
    expect(screen.getByTestId('action-release-payment')).toBeInTheDocument();
    expect(screen.getByTestId('action-add-note')).toBeInTheDocument();
  });

  it('renders the activity panel', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('activity-panel')).toBeInTheDocument();
  });

  it('links to the vendor portal', () => {
    render(<InvoiceDetailPage />);
    const vendorLink = screen.getByTestId('link-vendor-portal');
    expect(vendorLink).toHaveAttribute('href', '/demo/finance/vendor/VENDOR-001');
  });
});

describe('Invoice Detail Page - INV-2024-002 (Mismatch)', () => {
  beforeEach(() => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-002' });
  });

  it('shows mismatch warning for invoice with mismatch', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('mismatch-warning')).toBeInTheDocument();
    expect(screen.getByTestId('mismatch-warning')).toHaveTextContent('Mismatch Detected');
  });

  it('displays the correct vendor name', () => {
    render(<InvoiceDetailPage />);
    expect(screen.getByTestId('invoice-vendor')).toHaveTextContent('TechSupply Inc');
  });
});
