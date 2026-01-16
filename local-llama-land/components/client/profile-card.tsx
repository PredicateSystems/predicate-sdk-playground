'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button } from '../ui/button';
import { readSession } from '../../lib/auth';

type State =
  | { kind: 'loading'; delayMs: number }
  | { kind: 'ready'; username: string; email: string; editReady: boolean };

export function ProfileCard() {
  const [state, setState] = useState<State>({ kind: 'loading', delayMs: 0 });

  const delayMs = useMemo(() => {
    if (typeof window === 'undefined') return 900;
    const params = new URLSearchParams(window.location.search);
    const flaky = params.get('flaky') === '1';
    const base = 800 + Math.floor(Math.random() * 400); // requirement: 800–1200ms
    return flaky ? base + Math.floor(Math.random() * 800) : base;
  }, []);

  useEffect(() => {
    setState({ kind: 'loading', delayMs });
    const t = setTimeout(() => {
      const s = readSession();
      const username = s?.username ?? 'guest_llama';
      const email = s?.email ?? 'guest@localllama.land';
      setState({ kind: 'ready', username, email, editReady: false });

      // Edit button appears late (foot-gun)
      const t2 = setTimeout(() => {
        setState({ kind: 'ready', username, email, editReady: true });
      }, 900);

      return () => clearTimeout(t2);
    }, delayMs);

    return () => clearTimeout(t);
  }, [delayMs]);

  if (state.kind === 'loading') {
    return (
      <div className="glass rounded-xl p-6">
        <div className="text-sm text-white/70">Loading profile card…</div>
        <div className="mt-2 text-xs text-white/50">delay={state.delayMs}ms</div>
      </div>
    );
  }

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-start justify-between gap-6">
        <div className="space-y-1">
          <div className="text-xs text-white/60">Profile</div>
          <div className="text-xl font-semibold" data-testid="profile-username">
            {state.username}
          </div>
          <div className="text-sm text-white/70" data-testid="profile-email">
            {state.email}
          </div>
        </div>
        <Button variant="secondary" disabled={!state.editReady} aria-disabled={!state.editReady}>
          {state.editReady ? 'Edit profile' : 'Edit (loading…)'}
        </Button>
      </div>
    </div>
  );
}

