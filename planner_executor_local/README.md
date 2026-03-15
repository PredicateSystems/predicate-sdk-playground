## Planner + Executor (Local)

This folder is a starter for a **planner + executor** Amazon flow, modeled after
`amazon_shopping_with_assertions` (snapshots + `AgentRuntime` assertions per step).

- **Planner**: Qwen 3.5 9B (MLX 4-bit quantized) — produces a step plan
- **Executor**: Qwen 3.5 4B (MLX 4-bit quantized) — executes each step deterministically

> **Upgrade note**: We now use Qwen 3.5 models (9B planner, 4B executor) which provide better JSON output and reasoning compared to the older Qwen 2.5 models (7B/3B). The MLX 4-bit quantization runs efficiently on Apple Silicon.

### Model Recommendation (Apple Silicon)

**Default:** MLX with 4-bit quantized Qwen 3.5 models.

- **Apple Silicon (recommended)**: Uses MLX backend with `mlx-community/Qwen3.5-9B-MLX-4bit` (planner) and `mlx-community/Qwen3.5-4B-MLX-4bit` (executor). Fast and memory-efficient.
- **CUDA GPU available**: You can use HuggingFace Transformers with 4-bit quantization (`load_in_4bit=True`).
- **CPU-only**: Not recommended for 9B models; expect very slow runtimes.

### Prerequisites (MLX - Apple Silicon)

Install the MLX language model library:

```bash
pip install mlx-lm>=0.31.1
```

> **Important**: Version 0.31.1+ is required for Qwen 3.5 model support.

---

### Running on Other Platforms (Linux/Windows)

MLX is Apple Silicon only. For Linux or Windows, use one of the following approaches:

#### Option 1: NVIDIA CUDA GPU (Recommended for non-Mac)

Use HuggingFace Transformers with 4-bit quantization via `bitsandbytes`:

**Prerequisites:**

```bash
# Install PyTorch with CUDA support (adjust cuda version as needed)
pip install torch --index-url https://download.pytorch.org/whl/cu121

# Install transformers and quantization dependencies
pip install transformers>=4.40.0 accelerate bitsandbytes>=0.43.0
```

**Run with HuggingFace provider:**

```bash
export PLANNER_PROVIDER=hf \
PLANNER_MODEL=Qwen/Qwen2.5-7B-Instruct \
EXECUTOR_PROVIDER=hf \
EXECUTOR_MODEL=Qwen/Qwen2.5-3B-Instruct
python main.py
```

> **Note**: The HuggingFace provider automatically enables 4-bit quantization (`load_in_4bit=True`) when `bitsandbytes` is installed. For Qwen 3.5 models on HuggingFace, check model availability as MLX-specific quantizations won't work.

**VRAM requirements (approximate):**
- Qwen 2.5 7B (4-bit): ~6GB VRAM
- Qwen 2.5 3B (4-bit): ~3GB VRAM
- Combined: ~10GB VRAM minimum

#### Option 2: Windows with WSL2

If running on Windows, we recommend using WSL2 (Windows Subsystem for Linux) with Ubuntu:

1. Install WSL2: `wsl --install`
2. Install CUDA drivers for WSL2 from NVIDIA
3. Follow the Linux CUDA instructions above inside WSL2

#### Option 3: CPU-Only (Not Recommended)

Running 7B+ models on CPU is extremely slow (expect 10-30+ seconds per inference).

```bash
export PLANNER_PROVIDER=hf \
PLANNER_MODEL=Qwen/Qwen2.5-3B-Instruct \
EXECUTOR_PROVIDER=hf \
EXECUTOR_MODEL=Qwen/Qwen2.5-1.5B-Instruct
python main.py
```

> **Warning**: CPU inference for the planner will be very slow. Consider using smaller models (1.5B-3B) or a cloud API for the planner while running the executor locally.

#### Option 4: Cloud API for Planner, Local Executor

For best results on limited hardware, use a cloud API for the planner (reasoning-heavy) and run only the executor locally:

```bash
export PLANNER_PROVIDER=openai \
PLANNER_MODEL=gpt-4o-mini \
EXECUTOR_PROVIDER=hf \
EXECUTOR_MODEL=Qwen/Qwen2.5-3B-Instruct
python main.py
```

This hybrid approach gives you cloud-quality planning with local execution (no screenshots sent to cloud).

---

### Next Step

Run the scaffold:

```bash
python main.py
```

This scaffold includes:

- **Planner feedback loop**: executor failures are summarized back to the planner for a revised plan.
- **JSON schema validation**: plan output is validated against the advanced plan format.
- **Planner feedback JSONL**: per-run file in `planner_feedback/<run_id>.jsonl`.
- **Summary JSON**: compact summary at `planner_feedback/<run_id>.summary.json`.
- **Vision fallback (optional)**: set `ENABLE_VISION_FALLBACK=1`.

### Default Models (Qwen 3.5)

The script defaults to Qwen 3.5 MLX models on Apple Silicon:

```bash
# Default (no env vars needed on Apple Silicon)
python main.py
```

This uses:
- **Planner**: `mlx-community/Qwen3.5-9B-MLX-4bit`
- **Executor**: `mlx-community/Qwen3.5-4B-MLX-4bit`

### Custom Model Configuration

To override models or use different providers:

```bash
export PLANNER_PROVIDER=mlx \
PLANNER_MODEL=mlx-community/Qwen3.5-9B-MLX-4bit \
EXECUTOR_PROVIDER=mlx \
EXECUTOR_MODEL=mlx-community/Qwen3.5-4B-MLX-4bit
python main.py
```

For HuggingFace Transformers (CUDA):

```bash
export PLANNER_PROVIDER=hf \
PLANNER_MODEL=Qwen/Qwen2.5-7B-Instruct \
EXECUTOR_PROVIDER=hf \
EXECUTOR_MODEL=Qwen/Qwen2.5-3B-Instruct
python main.py
```

### Vision Fallback (optional)

By default, the executor is text-only. To enable vision fallback:

```bash
ENABLE_VISION_FALLBACK=1 \
VISION_PROVIDER=local \
VISION_MODEL=Qwen/Qwen3-VL-8B-Instruct \
python main.py
```

On Apple Silicon, you can use MLX-VLM:

```bash
ENABLE_VISION_FALLBACK=1 \
VISION_PROVIDER=mlx \
VISION_MODEL=mlx-community/Qwen3-VL-8B-Instruct-3bit \
python main.py
```

Vision fallback behavior:

- If executor cannot produce a `CLICK(<id>)`, vision selects an element ID from the snapshot list.
- If required verification fails after a click, vision can re-select a better element ID and retry.
- Vision responses are logged as `vision_select` events in the JSONL feedback.

If you want, I can add:

- A planner/executor scaffold script
- JSON step schema + validator
- Executor loop that maps plan steps to `AgentRuntime` assertions
- Planner feedback channel (executor writes assertion outcomes back to planner)
