import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import InvoiceDetailPage from '../../app/demo/finance/invoices/[id]/page';

// Mock next/navigation
const mockUseParams = vi.fn();
vi.mock('next/navigation', () => ({
  useParams: () => mockUseParams(),
}));

describe('Silent Failure Path - INV-2024-002 (Mismatch Invoice)', () => {
  beforeEach(() => {
    // INV-2024-002 has mismatch=true, so it will silently fail
    mockUseParams.mockReturnValue({ id: 'INV-2024-002' });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('identifies this invoice as one that will silently fail', () => {
    render(<InvoiceDetailPage />);

    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-will-silently-fail', 'true');
  });

  it('shows initial status as pending', () => {
    render(<InvoiceDetailPage />);

    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'pending');
  });

  it('opens modal when clicking Mark Reconciled', () => {
    render(<InvoiceDetailPage />);

    const markReconciledBtn = screen.getByTestId('action-mark-reconciled');
    fireEvent.click(markReconciledBtn);

    expect(screen.getByTestId('reconciliation-modal')).toBeInTheDocument();
    expect(screen.getByTestId('modal-confirm')).toBeInTheDocument();
  });

  it('shows processing state when confirming', async () => {
    render(<InvoiceDetailPage />);

    // Open modal
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));

    // Click confirm
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Should show processing
    expect(screen.getByTestId('processing-spinner')).toBeInTheDocument();
  });

  it('closes modal after processing but status DOES NOT change (silent failure)', async () => {
    render(<InvoiceDetailPage />);

    // Capture initial status
    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'pending');

    // Open modal
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    expect(screen.getByTestId('reconciliation-modal')).toBeInTheDocument();

    // Click confirm
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Advance timers past the simulated network delay (800ms)
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Modal should be closed
    expect(screen.queryByTestId('reconciliation-modal')).not.toBeInTheDocument();

    // KEY ASSERTION: Status should STILL be pending (not reconciled)
    // This is the silent failure - the action appeared to complete but state didn't change
    const updatedDebugInfo = screen.getByTestId('debug-info');
    expect(updatedDebugInfo).toHaveAttribute('data-current-status', 'pending');
  });

  it('status badge still shows "pending" after failed reconciliation attempt', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // The visible status badge should still show pending
    const statusBadge = screen.getByTestId('status-badge-reconciliation');
    expect(statusBadge).toHaveAttribute('data-status', 'pending');
    expect(statusBadge).toHaveTextContent('pending');
  });

  it('does NOT add a success note after silent failure', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Should not have a reconciliation success note
    expect(screen.queryByText('Reconciliation completed successfully.')).not.toBeInTheDocument();
  });
});

describe('Success Path - INV-2024-001 (No Mismatch)', () => {
  beforeEach(() => {
    // INV-2024-001 has mismatch=false, so it will succeed
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('identifies this invoice as one that will NOT silently fail', () => {
    render(<InvoiceDetailPage />);

    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-will-silently-fail', 'false');
  });

  it('successfully changes status to reconciled', async () => {
    render(<InvoiceDetailPage />);

    // Confirm initial status
    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'pending');

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Status should now be reconciled
    const updatedDebugInfo = screen.getByTestId('debug-info');
    expect(updatedDebugInfo).toHaveAttribute('data-current-status', 'reconciled');
  });

  it('status badge shows "reconciled" after successful reconciliation', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // The visible status badge should show reconciled
    const statusBadge = screen.getByTestId('status-badge-reconciliation');
    expect(statusBadge).toHaveAttribute('data-status', 'reconciled');
    expect(statusBadge).toHaveTextContent('reconciled');
  });

  it('adds a success note after successful reconciliation', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Should have a reconciliation success note
    expect(screen.getByText('Reconciliation completed successfully.')).toBeInTheDocument();
  });

  it('disables Mark Reconciled button after success', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and confirm
    fireEvent.click(screen.getByTestId('action-mark-reconciled'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for processing
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Button should be disabled
    const markReconciledBtn = screen.getByTestId('action-mark-reconciled');
    expect(markReconciledBtn).toBeDisabled();
  });
});

describe('Route To Review - Corrected Bounded Action', () => {
  beforeEach(() => {
    // Use the mismatch invoice - this proves Route To Review works even when Mark Reconciled fails
    mockUseParams.mockReturnValue({ id: 'INV-2024-002' });
  });

  it('successfully routes to review (the fallback action always works)', () => {
    render(<InvoiceDetailPage />);

    // Click Route To Review
    fireEvent.click(screen.getByTestId('action-route-to-review'));

    // Status should change to needs_review
    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'needs_review');
  });

  it('adds a note when routed to review', () => {
    render(<InvoiceDetailPage />);

    // Click Route To Review
    fireEvent.click(screen.getByTestId('action-route-to-review'));

    // Should have the review note
    expect(screen.getByText('Routed to review queue for manual inspection.')).toBeInTheDocument();
  });

  it('status badge shows "needs review" after routing', () => {
    render(<InvoiceDetailPage />);

    // Click Route To Review
    fireEvent.click(screen.getByTestId('action-route-to-review'));

    // The visible status badge should show needs_review
    const statusBadge = screen.getByTestId('status-badge-reconciliation');
    expect(statusBadge).toHaveAttribute('data-status', 'needs_review');
    expect(statusBadge).toHaveTextContent('needs review');
  });
});
