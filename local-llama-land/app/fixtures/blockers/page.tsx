import { BlockersFixtureClient } from '../../../components/client/blockers-fixture';

export default function BlockersFixturePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Blockers fixture</h1>
        <p className="text-white/70">
          Deterministic UI states for testing abort detection (login, captcha, modal, payment).
        </p>
      </div>
      <BlockersFixtureClient />
    </div>
  );
}

