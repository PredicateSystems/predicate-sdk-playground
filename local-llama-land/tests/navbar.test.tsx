import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Navbar } from '../components/navbar';

describe('Navbar', () => {
  it('shows the Predicate Systems attribution link', () => {
    render(<Navbar />);

    const predicateSystemsLink = screen.getByRole('link', { name: /predicate systems/i });
    expect(predicateSystemsLink).toBeInTheDocument();
    expect(predicateSystemsLink).toHaveAttribute('href', 'https://www.predicatesystems.ai');
  });
});
