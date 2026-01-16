'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Button } from '../../components/ui/button';
import { HydrationGate } from '../../components/client/hydration-gate';
import { ProfileCard } from '../../components/client/profile-card';
import { clearSession, readSession } from '../../lib/auth';
import { useRouter } from 'next/navigation';

export default function ProfilePage() {
  const router = useRouter();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    const s = readSession();
    setSignedIn(!!s);
  }, []);

  function signOut() {
    clearSession();
    router.push('/login');
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Your profile</h1>
          <p className="text-white/70">This page intentionally loads content late.</p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/dashboard">
            <Button variant="secondary">Dashboard</Button>
          </Link>
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>

      <HydrationGate label="Hydrating profile shell…" baseDelayMs={500} jitterMs={700}>
        {signedIn === false ? (
          <div className="glass rounded-xl p-6">
            <div className="text-sm text-white/70">Not signed in.</div>
            <div className="mt-3">
              <Link href="/login">
                <Button>Go to login</Button>
              </Link>
            </div>
          </div>
        ) : (
          <ProfileCard />
        )}
      </HydrationGate>

      <div className="glass rounded-xl p-6">
        <div className="text-sm font-semibold">Embedded activity (iframe)</div>
        <div className="mt-2 text-sm text-white/70">
          This iframe is here on purpose for demo #3 (agents must handle it).
        </div>
        <iframe
          className="mt-4 h-[220px] w-full rounded-lg border border-white/10 bg-black"
          src="/embed/activity"
          title="activity"
        />
      </div>
    </div>
  );
}

