# Local Llama Land (Fake Next.js Website)

This is the **fake Next.js SPA** used for public demos **#3–#5** in `docs/public_build_plan.md`.

Goals:
- Deterministic, repeatable UI flows for agents
- Built-in “foot-guns” that break naive scrapers (hydration delay, late content, disabled→enabled buttons, iframe)
- Clean, professional look using **Tailwind** (shadcn-style minimal components included locally)

## Routes

- `/login`
  - username + password
  - login button disabled until both filled
  - artificial delay before navigation
- `/profile`
  - profile card loads after ~800–1200ms
  - username rendered dynamically
  - “Edit profile” button appears late
  - includes an iframe
- `/dashboard`
  - KPI cards + table + chart placeholder
  - optional “live updates” mode to simulate DOM churn
- `/forms/onboarding`
  - multi-step form with validation gating each step
- `/fixtures/stabilize`
  - delayed hydration + timed DOM updates
  - optional `?live=1` for continuous DOM churn (should never “stabilize”)
- `/fixtures/reveal`
  - delayed hydration + scrollable results container
  - "Load more results" button appends items after a delay
  - pagination-like navigation via `?page=2`
- `/fixtures/blockers`
  - delayed hydration + deterministic blocker states via `?kind=...`
  - `?kind=captcha|login|payment|modal`

## Running

```bash
cd sentience-sdk-playground/local-llama-land
npm install
npm run dev
```

Then open `http://localhost:3000/login`.

## Demo toggles (useful for showcasing `.eventually()` and confidence)

- `?flaky=1`: increases randomness in delays
- `?live=1`: enables continuous updates on `/dashboard` to simulate DOM churn

