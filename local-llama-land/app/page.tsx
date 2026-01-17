import Link from 'next/link';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/80">
          Local Llama Land • Demo Site
        </div>
        <h1 className="text-4xl font-semibold tracking-tight">
          A clean Next.js mock social app built for agent verification demos.
        </h1>
        <p className="max-w-2xl text-white/70">
          Welcome to Local Llama Land! This demo site is designed for testing and demonstrating web automation agents.
          Feel free to explore and test your agents with realistic SPA patterns including delayed hydration, state transitions, and dynamic content.
          <span className="block mt-2 text-xs text-white/50">
            Note: Rate limiting is set to 30 requests per minute per IP to ensure fair usage for all testers.
          </span>
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href="/login">
            <Button>Go to Login</Button>
          </Link>
          <Link href="/dashboard">
            <Button variant="secondary">Open Dashboard</Button>
          </Link>
          <Link href="/forms/onboarding">
            <Button variant="secondary">Try Multi-step Form</Button>
          </Link>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card title="Delayed hydration" desc="UI initializes after a short delay (Suspense + timers)." />
        <Card title="Late content" desc="Profile + tables load after 800–1200ms to exercise retries." />
        <Card title="State transitions" desc="Disabled → enabled buttons gated by validation." />
      </section>
    </div>
  );
}
