'use client';

import { useMemo, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';

type Step = 1 | 2 | 3 | 4;

function isEmail(s: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());
}

export function OnboardingForm() {
  const [step, setStep] = useState<Step>(1);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [plan, setPlan] = useState<'free' | 'pro' | ''>('');
  const [agree, setAgree] = useState(false);
  const [pending, setPending] = useState(false);
  const [success, setSuccess] = useState(false);

  const canNext = useMemo(() => {
    if (step === 1) return isEmail(email);
    if (step === 2) return name.trim().length >= 2;
    if (step === 3) return plan !== '' && agree;
    return true;
  }, [step, email, name, plan, agree]);

  async function next() {
    if (!canNext || pending) return;
    setPending(true);
    const delay = 450 + Math.floor(Math.random() * 650);
    await new Promise(r => setTimeout(r, delay));
    setPending(false);
    setStep((step + 1) as Step);
  }

  async function submit() {
    if (pending) return;
    setPending(true);
    const delay = 900 + Math.floor(Math.random() * 900);
    await new Promise(r => setTimeout(r, delay));
    setPending(false);
    setSuccess(true);
  }

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Onboarding</div>
        <div className="text-xs text-white/60">Step {step} / 4</div>
      </div>

      <div className="mt-5 space-y-4">
        {step === 1 ? (
          <>
            <Input
              label="Email"
              name="email"
              placeholder="you@localllama.land"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <div className="text-xs text-white/60">
              Next is disabled until email is valid.
            </div>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <Input
              label="Display name"
              name="display_name"
              placeholder="Llama Rider"
              value={name}
              onChange={e => setName(e.target.value)}
            />
            <div className="text-xs text-white/60">Requires at least 2 characters.</div>
          </>
        ) : null}

        {step === 3 ? (
          <>
            <div className="space-y-2">
              <div className="text-sm text-white/80">Choose a plan</div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="plan"
                  value="free"
                  checked={plan === 'free'}
                  onChange={() => setPlan('free')}
                />
                Free
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="plan"
                  value="pro"
                  checked={plan === 'pro'}
                  onChange={() => setPlan('pro')}
                />
                Pro
              </label>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="agree"
                checked={agree}
                onChange={e => setAgree(e.target.checked)}
              />
              I agree to the Terms
            </label>

            <div className="text-xs text-white/60">
              Next is disabled until plan is selected and Terms is checked.
            </div>
          </>
        ) : null}

        {step === 4 ? (
          <>
            <div className="text-sm text-white/80">Review</div>
            <div className="rounded-lg border border-white/10 bg-black/30 p-4 text-sm">
              <div>
                <span className="text-white/60">Email:</span> {email || '—'}
              </div>
              <div>
                <span className="text-white/60">Name:</span> {name || '—'}
              </div>
              <div>
                <span className="text-white/60">Plan:</span> {plan || '—'}
              </div>
            </div>

            {success ? (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-200">
                Success! Your profile is ready.
              </div>
            ) : (
              <div className="rounded-lg border border-white/10 bg-white/5 p-4 text-sm text-white/70">
                CAPTCHA placeholder: <span className="text-white">“I am not a bot”</span> (no real CAPTCHA)
              </div>
            )}
          </>
        ) : null}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <Button
          variant="ghost"
          onClick={() => setStep((Math.max(1, step - 1) as Step))}
          disabled={pending || step === 1}
          aria-disabled={pending || step === 1}
        >
          Back
        </Button>

        {step < 4 ? (
          <Button onClick={next} disabled={!canNext || pending} aria-disabled={!canNext || pending}>
            {pending ? 'Working…' : 'Next'}
          </Button>
        ) : (
          <Button onClick={submit} disabled={pending || success} aria-disabled={pending || success}>
            {success ? 'Done' : pending ? 'Submitting…' : 'Submit'}
          </Button>
        )}
      </div>
    </div>
  );
}

