import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import VendorDetailPage from '../../app/demo/finance/vendor/[id]/page';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'VENDOR-001' }),
}));

describe('Vendor Detail Page', () => {
  it('renders the vendor name in the header', () => {
    render(<VendorDetailPage />);
    expect(screen.getByTestId('vendor-name')).toHaveTextContent('Acme Corp');
  });

  it('renders the vendor legal name', () => {
    render(<VendorDetailPage />);
    expect(screen.getByTestId('vendor-legal-name')).toHaveTextContent('Acme Corporation');
  });

  it('displays all required vendor fields', () => {
    render(<VendorDetailPage />);

    // Invoice record fields
    expect(screen.getByTestId('vendor-field-invoice-number')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-billed-amount')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-invoice-date')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-payment-state')).toBeInTheDocument();

    // Vendor information fields
    expect(screen.getByTestId('vendor-field-id')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-display-name')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-legal-name')).toBeInTheDocument();
    expect(screen.getByTestId('vendor-field-email')).toBeInTheDocument();
  });

  it('displays the correct billed amount', () => {
    render(<VendorDetailPage />);
    expect(screen.getByTestId('vendor-field-billed-amount-value')).toHaveTextContent('$12,500.00');
  });

  it('displays the invoice number matching the linked invoice', () => {
    render(<VendorDetailPage />);
    expect(screen.getByTestId('vendor-field-invoice-number-value')).toHaveTextContent('INV-2024-001');
  });

  it('renders the comparison table for verification', () => {
    render(<VendorDetailPage />);
    expect(screen.getByTestId('comparison-table')).toBeInTheDocument();

    // Check comparison values are present
    expect(screen.getByTestId('compare-invoice-number')).toHaveTextContent('INV-2024-001');
    expect(screen.getByTestId('compare-vendor-name')).toHaveTextContent('Acme Corp');
    expect(screen.getByTestId('compare-billed-amount')).toHaveTextContent('$12,500.00');
  });

  it('has external system styling (emerald theme)', () => {
    render(<VendorDetailPage />);
    // The page should have the vendor portal indicator
    expect(screen.getByText('VENDOR PORTAL')).toBeInTheDocument();
    expect(screen.getByText('External System')).toBeInTheDocument();
  });
});
