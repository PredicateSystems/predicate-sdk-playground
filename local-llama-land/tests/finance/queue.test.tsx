import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import InvoiceQueuePage from '../../app/demo/finance/queue/page';

describe('Invoice Queue Page', () => {
  it('renders the page title and invoice count', () => {
    render(<InvoiceQueuePage />);
    expect(screen.getByText('Invoice Queue')).toBeInTheDocument();
    expect(screen.getByText(/5 invoices/i)).toBeInTheDocument();
  });

  it('displays the invoice table with all columns', () => {
    render(<InvoiceQueuePage />);

    const table = screen.getByTestId('invoice-table');
    expect(table).toBeInTheDocument();

    // Check for column headers
    expect(screen.getByText('Invoice #')).toBeInTheDocument();
    expect(screen.getByText('Vendor')).toBeInTheDocument();
    expect(screen.getByText('Amount')).toBeInTheDocument();
    expect(screen.getByText('Due Date')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
    expect(screen.getByText('PO Ref')).toBeInTheDocument();
  });

  it('displays specific invoice data', () => {
    render(<InvoiceQueuePage />);

    // Check that INV-2024-001 is displayed
    expect(screen.getByText('INV-2024-001')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('$12,500.00')).toBeInTheDocument();

    // Check that INV-2024-002 with mismatch is displayed
    expect(screen.getByText('INV-2024-002')).toBeInTheDocument();
    expect(screen.getByText('TechSupply Inc')).toBeInTheDocument();
  });

  it('shows filter tabs', () => {
    render(<InvoiceQueuePage />);

    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'pending' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'reconciled' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'needs review' })).toBeInTheDocument();
  });

  it('links back to finance landing page', () => {
    render(<InvoiceQueuePage />);

    const backLink = screen.getByRole('link', { name: /back to finance/i });
    expect(backLink).toHaveAttribute('href', '/demo/finance');
  });
});
