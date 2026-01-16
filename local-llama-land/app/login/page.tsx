'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { HydrationGate } from '../../components/client/hydration-gate';
import { writeSession } from '../../lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);

  const canLogin = useMemo(() => username.trim().length > 0 && password.trim().length > 0, [
    username,
    password,
  ]);

  async function onLogin() {
    if (!canLogin || pending) return;
    setPending(true);

    // Artificial delay before navigation (foot-gun)
    const delay = 900 + Math.floor(Math.random() * 700);
    await new Promise(r => setTimeout(r, delay));

    writeSession({
      username: username.trim(),
      email: `${username.trim().toLowerCase()}@localllama.land`,
    });

    router.push('/profile');
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold">Sign in</h1>
        <p className="text-white/70">
          Welcome back to <span className="font-medium text-white">Local LLama Land</span>.
        </p>
      </div>

      <HydrationGate label="Hydrating login form…" baseDelayMs={600} jitterMs={800}>
        <div className="glass space-y-4 rounded-xl p-6">
          <Input
            label="Username"
            name="username"
            autoComplete="username"
            placeholder="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
          <Input
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />

          <div className="flex items-center justify-between pt-2">
            <div className="text-xs text-white/60">
              Tip: button stays disabled until both fields are filled.
            </div>
            <Button
              onClick={onLogin}
              disabled={!canLogin || pending}
              aria-disabled={!canLogin || pending}
            >
              {pending ? 'Signing in…' : 'Sign in'}
            </Button>
          </div>
        </div>
      </HydrationGate>
    </div>
  );
}

