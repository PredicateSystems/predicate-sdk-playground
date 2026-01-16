# 📰 News List Skimming Demo (Public Build)

This demo is the “public build” version of the unofficial flow you prototyped in:
`/Users/guoliangwang/Code/Python/browser-use/examples/integrations/sentience_multi_step_agent.py`

It is refactored to be **Sentience-SDK-only** (no `browser-use` dependency) and aligned with
`docs/public_build_plan.md`:

- **Tier 1 (primary)**: local text LLM (Qwen 2.5 3B) via `LocalLLMProvider`
- **Tier 2 (fallback)**: local vision LLM (Qwen3-VL) via `MLXVLMProvider` (preferred on Apple Silicon) or `LocalVisionLLMProvider`
- **Verification-first**: step assertions via `AgentRuntime` + `verification.py` predicates
- **Cloud trace sink**: `create_tracer(..., upload_trace=True)`
- **Humanized clicks**: opt-in `CursorPolicy(mode="human")`
- **Per-step metrics**: timestamps, durations, token usage summary (incl. retries)

## Quickstart

### 1) Install deps

From `sentience-sdk-playground/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r news_list_skimming/requirements.txt

# Install Sentience SDK from this monorepo
pip install -e ../sdk-python

playwright install chromium
```

### 2) Env vars

```bash
export SENTIENCE_API_KEY="sk_..."   # optional but recommended (enables cloud trace upload)

# Local text model (HF Transformers)
export LOCAL_TEXT_MODEL="Qwen/Qwen2.5-3B-Instruct"

# Vision fallback: pick ONE
# (A) MLX-VLM (best for Apple Silicon quantized)
export LOCAL_VISION_PROVIDER="mlx"
export LOCAL_VISION_MODEL="mlx-community/Qwen3-VL-8B-Instruct-3bit"

# (B) HF Transformers vision model
# export LOCAL_VISION_PROVIDER="hf"
# export LOCAL_VISION_MODEL="Qwen/Qwen3-VL-8B-Instruct"
```

### 3) Run

```bash
cd news_list_skimming
python main.py
```

## Notes

- This demo intentionally uses **Hacker News “Show”** because it’s stable and fast, which makes it
  ideal for public demos.
- If you want to force vision fallback for a recording, lower `max_snapshot_attempts` and raise
  `min_confidence` in `main.py`.

