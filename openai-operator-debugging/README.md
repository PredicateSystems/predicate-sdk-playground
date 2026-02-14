# OpenAI computer-use + PredicateDebugger (Playground Demo)

This demo shows how to use OpenAI's **computer use** loop (CUA) as an *action proposer* while using **Predicate** as a deterministic verification + trace sidecar.

It is modeled after `sentience-sdk-playground/browser-use-debugging`, but:

- OpenAI (`computer-use-preview`) proposes UI actions (`click`, `type`, `scroll`, `wait`, ...)
- We execute those actions in a local Playwright Chromium session
- Predicate attaches to the same Playwright `Page` and enforces:
  - **per-step required checks** (e.g. stay on-domain)
  - **task proof-of-done** (extract 3 featured headlines from Esquire)

## Task (WebBench #449)

Navigate to the Esquire homepage and list the headlines of the top 3 featured articles.  
Only use `esquire.com`.

## Install

From repo root (use your existing playground venv):

```bash
pip install -U openai playwright python-dotenv
playwright install chromium
```

## Configure environment

This demo loads env vars from:

- `sentience-sdk-playground/.env`
- `./.env` (current working directory)

Required:

- `OPENAI_API_KEY`

Optional (for uploading traces to Predicate Studio):

- `PREDICATE_API_KEY`

## Run

```bash
python sentience-sdk-playground/openai-operator-debugging/main.py
```

Useful toggles:

- `DEMO_MODE=fix` (default): normal run
- `DEMO_MODE=fail`: intentionally fails a required `task_complete` check at the end
- `OPENAI_MODEL=computer-use-preview` (required)
- `OPENAI_COMPUTER_TOOL_TYPE=computer-preview` (default; matches OpenAI CUA sample app)
- `MAX_STEPS=30`

Artifacts are written under:

- `sentience-sdk-playground/openai-operator-debugging/artifacts/<timestamp>/trace.jsonl`
- `.../screenshots/*.jpeg`
- `.../result.json`

