'use client';

import { useEffect, useMemo, useState } from 'react';
import { HydrationGate } from './hydration-gate';

type Row = { id: string; label: string };

/**
 * A deterministic fixture for testing stabilization logic.
 *
 * Behavior:
 * - Uses HydrationGate (delayed mount) to simulate hydration delay.
 * - After mount, performs a couple of timed DOM updates, then becomes stable.
 * - If ?live=1 is present, keeps mutating DOM every ~350ms (never stabilizes).
 */
export function StabilizeFixtureClient() {
  const [phase, setPhase] = useState<'LOADING' | 'READY' | 'READY!'>('LOADING');
  const [rows, setRows] = useState<Row[]>([]);

  const live = useMemo(() => {
    if (typeof window === 'undefined') return false;
    const params = new URLSearchParams(window.location.search);
    return params.get('live') === '1';
  }, []);

  useEffect(() => {
    // Two deterministic updates after hydration.
    const t1 = setTimeout(() => setPhase('READY'), 600);
    const t2 = setTimeout(() => setPhase('READY!'), 1100);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  useEffect(() => {
    // Structural churn: add/remove list items at a steady cadence.
    // Useful for verifying stabilize timeouts in "live" mode.
    if (!live) return;
    const t = setInterval(() => {
      setRows(prev => {
        const next = [...prev];
        next.unshift({ id: String(Date.now()), label: 'Live tick' });
        if (next.length > 5) next.pop();
        return next;
      });
    }, 350);
    return () => clearInterval(t);
  }, [live]);

  // For non-live mode, add one row after "READY!" to ensure one more digest change,
  // then remain stable.
  useEffect(() => {
    if (live) return;
    if (phase !== 'READY!') return;
    const t = setTimeout(() => {
      setRows([{ id: 'stable', label: 'Stable content' }]);
    }, 250);
    return () => clearTimeout(t);
  }, [phase, live]);

  return (
    <HydrationGate label="Hydrating stabilize fixture…" baseDelayMs={600} jitterMs={600}>
      <div className="glass rounded-xl p-6 space-y-4">
        <div>
          <div className="text-sm font-semibold">StabilizeGate fixture</div>
          <div className="text-xs text-white/60">
            Delayed hydration + timed updates; add <code className="text-white">?live=1</code> for DOM churn.
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/30 p-4">
          <div className="text-xs text-white/60">Status</div>
          <div className="mt-2 text-3xl font-semibold" data-testid="stabilize-status">
            {phase}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/30 p-4">
          <div className="text-xs text-white/60">Rows</div>
          {rows.length === 0 ? (
            <div className="mt-2 text-sm text-white/70" data-testid="stabilize-rows-empty">
              (none yet)
            </div>
          ) : (
            <ul className="mt-2 space-y-1" data-testid="stabilize-rows">
              {rows.map(r => (
                <li key={r.id} className="text-sm">
                  {r.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </HydrationGate>
  );
}

