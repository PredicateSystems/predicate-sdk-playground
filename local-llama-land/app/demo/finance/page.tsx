import Link from 'next/link';

export default function FinanceLandingPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold">Finance Operations Demo</h1>
        <p className="text-white/70 mt-2">
          Invoice exception triage workflow with pre-execution authorization and post-execution verification.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Link
          href="/demo/finance/queue"
          className="block p-6 rounded-lg border border-white/20 hover:border-white/40 transition-colors"
        >
          <h2 className="text-xl font-medium mb-2">Invoice Queue</h2>
          <p className="text-white/60 text-sm">
            View and triage pending invoices. Compare invoice fields across systems and detect mismatches.
          </p>
          <div className="mt-4 text-sm text-blue-400">Open Queue →</div>
        </Link>

        <Link
          href="/demo/finance/review"
          className="block p-6 rounded-lg border border-white/20 hover:border-white/40 transition-colors"
        >
          <h2 className="text-xl font-medium mb-2">Review Queue</h2>
          <p className="text-white/60 text-sm">
            Cases routed for manual review. View exception reasons and resolution notes.
          </p>
          <div className="mt-4 text-sm text-blue-400">Open Review →</div>
        </Link>
      </div>

      <div className="p-4 rounded-lg bg-white/5 border border-white/10">
        <h3 className="text-sm font-medium text-white/80 mb-2">Demo Story</h3>
        <ol className="text-sm text-white/60 space-y-1 list-decimal list-inside">
          <li>Normal flow: open invoice, compare fields, add note</li>
          <li>Silent failure: click "Mark Reconciled" but UI doesn't change</li>
          <li>Policy violation: attempt "Release Payment" — denied by sidecar</li>
          <li>Corrected action: "Route To Review" — allowed and verified</li>
        </ol>
      </div>
    </div>
  );
}
