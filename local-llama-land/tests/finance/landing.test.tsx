import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import FinanceLandingPage from '../../app/demo/finance/page';

describe('Finance Landing Page', () => {
  it('renders the page title', () => {
    render(<FinanceLandingPage />);
    expect(screen.getByText('Finance Operations Demo')).toBeInTheDocument();
  });

  it('shows navigation links to queue and review pages', () => {
    render(<FinanceLandingPage />);

    // Check for Invoice Queue link
    const queueLink = screen.getByRole('link', { name: /invoice queue/i });
    expect(queueLink).toBeInTheDocument();
    expect(queueLink).toHaveAttribute('href', '/demo/finance/queue');

    // Check for Review Queue link
    const reviewLink = screen.getByRole('link', { name: /review queue/i });
    expect(reviewLink).toBeInTheDocument();
    expect(reviewLink).toHaveAttribute('href', '/demo/finance/review');
  });

  it('displays the demo story steps', () => {
    render(<FinanceLandingPage />);

    expect(screen.getByText(/normal flow/i)).toBeInTheDocument();
    expect(screen.getByText(/silent failure/i)).toBeInTheDocument();
    expect(screen.getByText(/policy violation/i)).toBeInTheDocument();
    expect(screen.getByText(/corrected action/i)).toBeInTheDocument();
  });
});
