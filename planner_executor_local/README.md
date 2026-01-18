## Planner + Executor (Local)

This folder is a starter for a **planner + executor** Amazon flow, modeled after
`amazon_shopping_with_assertions` (snapshots + `AgentRuntime` assertions per step).

- **Planner**: Qwen 2.5 7B (produces a step plan)
- **Executor**: Qwen 2.5 3B (executes each step deterministically)

### Model Recommendation (7B)

**Short answer (public repo default):** use **MPS** (or `auto`) with **fp16/bf16**.

- **Apple Silicon / MPS**: Bitsandbytes 4-bit is not supported. Use `torch_dtype=torch.float16` and `device_map="mps"` (or `auto`). This is the recommended public default.
- **CUDA GPU available**: You can use 4-bit (`load_in_4bit=True`) for memory headroom.
- **CPU-only**: The 7B model will be slow; expect long runtimes.

This keeps the code consistent with the 3B HF transformer path while adapting to hardware constraints.

### Warm-up Download (7B)

This script downloads the 7B model weights into the HF cache without loading the model:

```bash
python download_qwen25_7b.py
```

Optional environment variables:

- `HF_HOME` or `TRANSFORMERS_CACHE` to control cache location
- `HF_TOKEN` if your environment requires authentication

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
