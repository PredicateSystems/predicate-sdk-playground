import Link from 'next/link';
import { Button } from '../../components/ui/button';

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <section className="space-y-4">
        <h1 className="text-4xl font-semibold tracking-tight">About Local Llama Land</h1>
        <p className="text-lg text-white/70">
          A public SPA playground designed for testing and demonstrating browser automation agents.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">What is this site?</h2>
        <p className="text-white/70">
          Local Llama Land is a purpose-built Next.js application that simulates realistic web patterns
          commonly found in modern SPAs. It serves as a controlled environment for testing browser agents
          without the unpredictability of real-world sites.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Why does it exist?</h2>
        <div className="space-y-3 text-white/70">
          <p>
            Testing browser automation on live websites is challenging: layouts change, content drifts,
            and bot defenses can interfere. This site provides a stable, deterministic environment where
            agents can be tested repeatably.
          </p>
          <p>
            Every feature here is intentional &mdash; the delays, the state transitions, the dynamic content.
            This allows developers to verify their agents handle real-world patterns correctly.
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Features for Testing</h2>
        <ul className="list-inside list-disc space-y-2 text-white/70">
          <li>
            <strong className="text-white">Delayed Hydration:</strong> UI components load after configurable delays (600-1500ms)
          </li>
          <li>
            <strong className="text-white">State Transitions:</strong> Buttons that start disabled and become enabled based on form validation
          </li>
          <li>
            <strong className="text-white">Late-loading Content:</strong> Profile cards and tables that appear after the initial page load
          </li>
          <li>
            <strong className="text-white">Dynamic DOM Updates:</strong> Dashboard with optional live mode that updates every 400ms
          </li>
          <li>
            <strong className="text-white">Multi-step Forms:</strong> Form flows with validation at each step
          </li>
          <li>
            <strong className="text-white">Realistic Login Flow:</strong> Username/password authentication with navigation
          </li>
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Demo Scenarios</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="glass rounded-xl p-5">
            <h3 className="font-semibold">Login + Profile</h3>
            <p className="mt-2 text-sm text-white/60">
              Navigate to login, fill credentials, wait for button to enable, sign in,
              then extract profile data from a late-loading card.
            </p>
          </div>
          <div className="glass rounded-xl p-5">
            <h3 className="font-semibold">Dashboard KPI Extraction</h3>
            <p className="mt-2 text-sm text-white/60">
              Load the dashboard, wait for KPI cards to hydrate, extract values,
              then optionally enable live mode to test DOM churn resilience.
            </p>
          </div>
          <div className="glass rounded-xl p-5">
            <h3 className="font-semibold">Multi-step Form</h3>
            <p className="mt-2 text-sm text-white/60">
              Complete a multi-step onboarding form with validation at each stage,
              proving correct state handling throughout.
            </p>
          </div>
          <div className="glass rounded-xl p-5">
            <h3 className="font-semibold">DOM Churn Stress Test</h3>
            <p className="mt-2 text-sm text-white/60">
              Enable live updates on the dashboard to simulate rapidly changing DOM,
              then verify stable elements can still be extracted.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Technical Details</h2>
        <ul className="list-inside list-disc space-y-2 text-white/70">
          <li>Built with Next.js 14 (App Router)</li>
          <li>Styled with Tailwind CSS</li>
          <li>No external API dependencies</li>
          <li>Fully client-side state management</li>
          <li>Configurable delay parameters</li>
        </ul>
      </section>

      <section className="space-y-4 border-t border-white/10 pt-8">
        <h2 className="text-2xl font-semibold">Try It Out</h2>
        <p className="text-white/70">
          Explore the site to see how your browser agent handles modern SPA patterns.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link href="/login">
            <Button>Start with Login</Button>
          </Link>
          <Link href="/dashboard">
            <Button variant="secondary">View Dashboard</Button>
          </Link>
          <Link href="/forms/onboarding">
            <Button variant="secondary">Try Multi-step Form</Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
