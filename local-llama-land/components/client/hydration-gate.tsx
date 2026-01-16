'use client';

import { useEffect, useMemo, useState } from 'react';

/**
 * Delayed hydration gate (SPA foot-gun).
 * - Shows a placeholder first
 * - Mounts children after a delay (optionally randomized when ?flaky=1)
 */
export function HydrationGate({
  children,
  baseDelayMs = 600,
  jitterMs = 600,
  label = 'Hydrating…',
}: {
  children: React.ReactNode;
  baseDelayMs?: number;
  jitterMs?: number;
  label?: string;
}) {
  const [ready, setReady] = useState(false);

  const delayMs = useMemo(() => {
    if (typeof window === 'undefined') return baseDelayMs;
    const params = new URLSearchParams(window.location.search);
    const flaky = params.get('flaky') === '1';
    if (!flaky) return baseDelayMs;
    return baseDelayMs + Math.floor(Math.random() * jitterMs);
  }, [baseDelayMs, jitterMs]);

  useEffect(() => {
    const t = setTimeout(() => setReady(true), delayMs);
    return () => clearTimeout(t);
  }, [delayMs]);

  if (!ready) {
    return (
      <div className="glass rounded-xl p-5 text-sm text-white/70" data-testid="hydration-gate">
        {label} (delay={delayMs}ms)
      </div>
    );
  }

  return <>{children}</>;
}

