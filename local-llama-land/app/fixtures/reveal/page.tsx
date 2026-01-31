import { RevealFixtureClient } from '../../../components/client/reveal-fixture';

export default function RevealFixturePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Reveal fixture</h1>
        <p className="text-white/70">
          A deterministic route for testing list/result reveal strategies (container scroll, load more, pagination).
        </p>
        <p className="text-xs text-white/50">
          Use <code className="text-white">?page=2</code> to switch pages.
        </p>
        <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-sm font-semibold">Suggested task (for agents)</div>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-white/70">
            <li>Confirm you can read the first three result titles (Page1 Result 1–3).</li>
            <li>Click <span className="text-white">Load more results</span> and verify more results appear.</li>
            <li>Use <span className="text-white">Next page</span> (or <code className="text-white">?page=2</code>) and verify titles change to Page2.</li>
          </ol>
          <div className="mt-2 text-xs text-white/50">
            This page includes delayed hydration, a scrollable container, an accordion-like “Filters” control, load-more, and pagination.
          </div>
        </div>
      </div>
      <RevealFixtureClient />
    </div>
  );
}

