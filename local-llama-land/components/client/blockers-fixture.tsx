'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { Button } from '../ui/button';
import { HydrationGate } from './hydration-gate';
import { Input } from '../ui/input';

type Kind = 'captcha' | 'login' | 'payment' | 'modal';

function getKind(): Kind {
  if (typeof window === 'undefined') return 'captcha';
  const params = new URLSearchParams(window.location.search);
  const k = String(params.get('kind') || 'captcha');
  if (k === 'login' || k === 'payment' || k === 'modal' || k === 'captcha') return k;
  return 'captcha';
}

export function BlockersFixtureClient() {
  const kind = useMemo(() => getKind(), []);

  return (
    <HydrationGate label="Hydrating blockers fixture…" baseDelayMs={500} jitterMs={400}>
      <div className="glass rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold">Blockers fixture</div>
            <div className="text-xs text-white/60">
              Used to test Phase 5 abort taxonomy detection (login/captcha/modal/payment).
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/fixtures/blockers?kind=captcha">
              <Button variant={kind === 'captcha' ? 'secondary' : 'ghost'}>Captcha</Button>
            </Link>
            <Link href="/fixtures/blockers?kind=login">
              <Button variant={kind === 'login' ? 'secondary' : 'ghost'}>Login</Button>
            </Link>
            <Link href="/fixtures/blockers?kind=payment">
              <Button variant={kind === 'payment' ? 'secondary' : 'ghost'}>Payment</Button>
            </Link>
            <Link href="/fixtures/blockers?kind=modal">
              <Button variant={kind === 'modal' ? 'secondary' : 'ghost'}>Modal</Button>
            </Link>
          </div>
        </div>

        {kind === 'captcha' ? (
          <div className="rounded-lg border border-white/10 bg-black/30 p-4 space-y-2">
            <div className="text-sm font-semibold">Human verification</div>
            <div className="text-sm text-white/80">I&apos;m not a robot</div>
            <div className="text-xs text-white/60">reCAPTCHA</div>
          </div>
        ) : null}

        {kind === 'login' ? (
          <div className="rounded-lg border border-white/10 bg-black/30 p-4 space-y-3">
            <div className="text-sm font-semibold">Sign in</div>
            <Input label="Email" name="email" placeholder="you@example.com" />
            <Input label="Password" name="password" placeholder="••••••••" type="password" />
            <Button disabled aria-disabled>
              Continue
            </Button>
          </div>
        ) : null}

        {kind === 'payment' ? (
          <div className="rounded-lg border border-white/10 bg-black/30 p-4 space-y-3">
            <div className="text-sm font-semibold">Subscribe to continue</div>
            <div className="text-xs text-white/60">Payment required</div>
            <Input label="Card number" name="card_number" placeholder="4242 4242 4242 4242" />
            <Button>Checkout</Button>
          </div>
        ) : null}

        {kind === 'modal' ? (
          <div className="relative rounded-lg border border-white/10 bg-black/30 p-4">
            <div className="text-xs text-white/60">Background content (should be blocked)</div>
            <div className="mt-4 h-24 rounded-md border border-white/10 bg-white/5" />

            {/* Modal overlay */}
            <div className="absolute inset-0 bg-black/60" aria-hidden="true" />
            <div
              role="dialog"
              aria-modal="true"
              className="absolute left-1/2 top-1/2 w-[min(520px,90%)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-zinc-950 p-5 shadow-xl"
            >
              <div className="text-sm font-semibold">Cookie settings</div>
              <div className="mt-2 text-xs text-white/60">This modal blocks clicks until dismissed.</div>
              <div className="mt-4 flex gap-2">
                <Button variant="secondary">Accept</Button>
                <Button variant="ghost">Reject</Button>
              </div>
            </div>
          </div>
        ) : null}

        <div className="rounded-lg border border-white/10 bg-white/5 p-4 text-xs text-white/70">
          Suggested task (for agents): “Try to click around or proceed. If blocked, identify whether it’s login,
          captcha, modal, or payment-required.”
        </div>
      </div>
    </HydrationGate>
  );
}

