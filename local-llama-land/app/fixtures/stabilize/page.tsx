import { StabilizeFixtureClient } from '../../../components/client/stabilize-fixture';

export default function StabilizeFixturePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Stabilize fixture</h1>
        <p className="text-white/70">
          A deterministic route for testing post-action stabilization (delayed hydration + timed DOM updates).
        </p>
        <p className="text-xs text-white/50">
          Tip: add <code className="text-white">?live=1</code> to simulate continuous DOM churn.
        </p>
      </div>
      <StabilizeFixtureClient />
    </div>
  );
}

