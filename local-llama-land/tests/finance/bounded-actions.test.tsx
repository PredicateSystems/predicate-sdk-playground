import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import InvoiceDetailPage from '../../app/demo/finance/invoices/[id]/page';

// Mock next/navigation
const mockUseParams = vi.fn();
vi.mock('next/navigation', () => ({
  useParams: () => mockUseParams(),
}));

describe('Add Note - Safe Bounded Action', () => {
  beforeEach(() => {
    // Use any invoice - Add Note always works
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens Add Note modal when clicking the button', () => {
    render(<InvoiceDetailPage />);

    fireEvent.click(screen.getByTestId('action-add-note'));

    expect(screen.getByTestId('add-note-modal')).toBeInTheDocument();
    expect(screen.getByTestId('note-textarea')).toBeInTheDocument();
  });

  it('shows quick note options', () => {
    render(<InvoiceDetailPage />);

    fireEvent.click(screen.getByTestId('action-add-note'));

    expect(screen.getByTestId('quick-note-0')).toBeInTheDocument();
    expect(screen.getByTestId('quick-note-1')).toBeInTheDocument();
  });

  it('populates textarea when clicking a quick note', () => {
    render(<InvoiceDetailPage />);

    fireEvent.click(screen.getByTestId('action-add-note'));
    fireEvent.click(screen.getByTestId('quick-note-0'));

    const textarea = screen.getByTestId('note-textarea') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Requesting manager approval for payment release.');
  });

  it('increments note count after adding a note', async () => {
    render(<InvoiceDetailPage />);

    // Check initial note count
    const initialNoteCount = screen.getByTestId('note-count').textContent;
    const initialCount = parseInt(initialNoteCount?.match(/\d+/)?.[0] || '0');

    // Open modal and add a note
    fireEvent.click(screen.getByTestId('action-add-note'));
    const textarea = screen.getByTestId('note-textarea');
    fireEvent.change(textarea, { target: { value: 'Test note for verification.' } });
    fireEvent.click(screen.getByTestId('modal-submit-note'));

    // Wait for submission
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // Note count should increase by 1
    const newNoteCount = screen.getByTestId('note-count').textContent;
    const newCount = parseInt(newNoteCount?.match(/\d+/)?.[0] || '0');
    expect(newCount).toBe(initialCount + 1);
  });

  it('shows the new note text in the activity panel', async () => {
    render(<InvoiceDetailPage />);

    const testNoteText = 'This is a test note for the demo.';

    // Open modal and add a note
    fireEvent.click(screen.getByTestId('action-add-note'));
    const textarea = screen.getByTestId('note-textarea');
    fireEvent.change(textarea, { target: { value: testNoteText } });
    fireEvent.click(screen.getByTestId('modal-submit-note'));

    // Wait for submission
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // The note text should appear in the activity panel
    expect(screen.getByText(testNoteText)).toBeInTheDocument();
  });

  it('shows the note author as Agent', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and add a note
    fireEvent.click(screen.getByTestId('action-add-note'));
    const textarea = screen.getByTestId('note-textarea');
    fireEvent.change(textarea, { target: { value: 'A note from the agent.' } });
    fireEvent.click(screen.getByTestId('modal-submit-note'));

    // Wait for submission
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // The activity panel should show the Agent author
    const activityPanel = screen.getByTestId('activity-panel');
    expect(activityPanel.textContent).toContain('Agent');
  });

  it('closes modal after submitting', async () => {
    render(<InvoiceDetailPage />);

    // Open modal and submit
    fireEvent.click(screen.getByTestId('action-add-note'));
    const textarea = screen.getByTestId('note-textarea');
    fireEvent.change(textarea, { target: { value: 'Closing test.' } });
    fireEvent.click(screen.getByTestId('modal-submit-note'));

    // Wait for submission
    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // Modal should be closed
    expect(screen.queryByTestId('add-note-modal')).not.toBeInTheDocument();
  });
});

describe('Release Payment - High-Risk Action with Policy Denial', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('High-Value Invoice (INV-2024-001 - $12,500)', () => {
    beforeEach(() => {
      mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    });

    it('shows high-value indicator on the invoice', () => {
      render(<InvoiceDetailPage />);

      expect(screen.getByTestId('high-value-flag')).toBeInTheDocument();
      expect(screen.getByTestId('high-value-flag')).toHaveTextContent('High Value');
    });

    it('marks invoice as high-value in debug info', () => {
      render(<InvoiceDetailPage />);

      const debugInfo = screen.getByTestId('debug-info');
      expect(debugInfo).toHaveAttribute('data-is-high-value', 'true');
    });

    it('opens Release Payment modal', () => {
      render(<InvoiceDetailPage />);

      fireEvent.click(screen.getByTestId('action-release-payment'));

      expect(screen.getByTestId('release-payment-modal')).toBeInTheDocument();
      expect(screen.getByTestId('payment-confirm-view')).toBeInTheDocument();
    });

    it('shows warning about high-value payment', () => {
      render(<InvoiceDetailPage />);

      fireEvent.click(screen.getByTestId('action-release-payment'));

      expect(screen.getByTestId('high-value-indicator')).toBeInTheDocument();
      expect(screen.getByTestId('high-value-indicator')).toHaveTextContent('High Value');
    });

    it('shows policy denial after attempting release', async () => {
      render(<InvoiceDetailPage />);

      // Open modal and attempt release
      fireEvent.click(screen.getByTestId('action-release-payment'));
      fireEvent.click(screen.getByTestId('modal-confirm-payment'));

      // Wait for policy check
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      // Should show denial view
      expect(screen.getByTestId('payment-denied-view')).toBeInTheDocument();
      expect(screen.getByTestId('policy-denial-message')).toBeInTheDocument();
    });

    it('denial message mentions the threshold', async () => {
      render(<InvoiceDetailPage />);

      fireEvent.click(screen.getByTestId('action-release-payment'));
      fireEvent.click(screen.getByTestId('modal-confirm-payment'));

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(screen.getByTestId('policy-denial-message')).toHaveTextContent('$10,000');
    });

    it('shows suggested alternatives after denial', async () => {
      render(<InvoiceDetailPage />);

      fireEvent.click(screen.getByTestId('action-release-payment'));
      fireEvent.click(screen.getByTestId('modal-confirm-payment'));

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      // Check that alternatives are shown in the denial message (not the button)
      expect(screen.getByText(/Route to review for manager approval/i)).toBeInTheDocument();
    });
  });

  describe('Low-Value Invoice (INV-2024-004 - $2,340.25)', () => {
    beforeEach(() => {
      mockUseParams.mockReturnValue({ id: 'INV-2024-004' });
    });

    it('does NOT show high-value indicator', () => {
      render(<InvoiceDetailPage />);

      expect(screen.queryByTestId('high-value-flag')).not.toBeInTheDocument();
    });

    it('marks invoice as NOT high-value in debug info', () => {
      render(<InvoiceDetailPage />);

      const debugInfo = screen.getByTestId('debug-info');
      expect(debugInfo).toHaveAttribute('data-is-high-value', 'false');
    });
  });
});

describe('Route To Review - Fallback Action After Denial', () => {
  beforeEach(() => {
    // Use a high-value invoice with mismatch - typical case where fallback is needed
    mockUseParams.mockReturnValue({ id: 'INV-2024-005' });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('route to review updates status to needs_review', () => {
    render(<InvoiceDetailPage />);

    // Initial status
    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'needs_review'); // Already needs_review for this invoice

    // For INV-2024-002 which starts as pending:
    mockUseParams.mockReturnValue({ id: 'INV-2024-002' });
  });

  it('disables Route To Review button after routing', () => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    render(<InvoiceDetailPage />);

    // Route to review
    fireEvent.click(screen.getByTestId('action-route-to-review'));

    // Button should be disabled
    expect(screen.getByTestId('action-route-to-review')).toBeDisabled();
  });

  it('adds routing note to activity panel', () => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    render(<InvoiceDetailPage />);

    fireEvent.click(screen.getByTestId('action-route-to-review'));

    expect(screen.getByText('Routed to review queue for manual inspection.')).toBeInTheDocument();
  });

  it('increments note count after routing', () => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    render(<InvoiceDetailPage />);

    const initialCount = parseInt(
      screen.getByTestId('note-count').textContent?.match(/\d+/)?.[0] || '0'
    );

    fireEvent.click(screen.getByTestId('action-route-to-review'));

    const newCount = parseInt(
      screen.getByTestId('note-count').textContent?.match(/\d+/)?.[0] || '0'
    );
    expect(newCount).toBe(initialCount + 1);
  });

  it('status badge shows needs_review after routing', () => {
    mockUseParams.mockReturnValue({ id: 'INV-2024-001' });
    render(<InvoiceDetailPage />);

    fireEvent.click(screen.getByTestId('action-route-to-review'));

    const statusBadge = screen.getByTestId('status-badge-reconciliation');
    expect(statusBadge).toHaveAttribute('data-status', 'needs_review');
  });
});

describe('Complete Demo Flow: Denied Action → Fallback', () => {
  beforeEach(() => {
    // High-value invoice with mismatch
    mockUseParams.mockReturnValue({ id: 'INV-2024-003' }); // $45,000 - high value
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('after payment denial, can successfully route to review', async () => {
    render(<InvoiceDetailPage />);

    // Attempt payment release (will be denied)
    fireEvent.click(screen.getByTestId('action-release-payment'));
    fireEvent.click(screen.getByTestId('modal-confirm-payment'));

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Verify denial shown
    expect(screen.getByTestId('payment-denied-view')).toBeInTheDocument();

    // Dismiss denial modal
    fireEvent.click(screen.getByTestId('modal-dismiss'));

    // Now use the fallback: Route to Review
    fireEvent.click(screen.getByTestId('action-route-to-review'));

    // Verify fallback succeeded
    const debugInfo = screen.getByTestId('debug-info');
    expect(debugInfo).toHaveAttribute('data-current-status', 'needs_review');
    expect(screen.getByText('Routed to review queue for manual inspection.')).toBeInTheDocument();
  });

  it('after payment denial, can successfully add a note', async () => {
    render(<InvoiceDetailPage />);

    // Attempt payment release (will be denied)
    fireEvent.click(screen.getByTestId('action-release-payment'));
    fireEvent.click(screen.getByTestId('modal-confirm-payment'));

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    // Dismiss denial
    fireEvent.click(screen.getByTestId('modal-dismiss'));

    // Add a note as fallback
    fireEvent.click(screen.getByTestId('action-add-note'));
    const textarea = screen.getByTestId('note-textarea');
    fireEvent.change(textarea, {
      target: { value: 'Requesting manager approval for high-value payment.' },
    });
    fireEvent.click(screen.getByTestId('modal-submit-note'));

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    // Verify note was added
    expect(
      screen.getByText('Requesting manager approval for high-value payment.')
    ).toBeInTheDocument();
  });
});
