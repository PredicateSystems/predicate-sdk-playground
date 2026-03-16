# Planner + Executor Demo (SDK AutomationTask)

This demo showcases the SDK's `PlannerExecutorAgent` with the abstracted `AutomationTask` model. Unlike `planner_executor_local` (which implements everything from scratch), this demo uses the SDK's built-in components.

## Features

- **AutomationTask**: Flexible task definition with categories, success criteria, and recovery
- **CAPTCHA Handling**: Multiple solver strategies (abort, human handoff, external solver)
- **Modal Dismissal**: Heuristic-based detection of modals and dialogs
- **Recovery/Rollback**: Automatic checkpoint creation and rollback on failure
- **Custom Heuristics**: Domain-specific element selection for e-commerce sites
- **Auth Boundary Detection**: Automatic detection and graceful handling of login/signin pages
- **Scroll-After-Escalation**: Adaptive viewport-based scrolling to find off-screen elements

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AutomationTask                           │
│  - task_id, starting_url, task (natural language)          │
│  - category (TRANSACTION, SEARCH, etc.)                    │
│  - success_criteria, recovery config                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  PlannerExecutorAgent                       │
├─────────────────────────────────────────────────────────────┤
│  Planner (gpt-4o)          │  Executor (gpt-4o-mini)       │
│  ─────────────             │  ────────────────             │
│  • JSON plan generation    │  • Step execution             │
│  • Replanning on failure   │  • Heuristics + LLM fallback  │
│  • Predicate verification  │  • Vision fallback            │
├─────────────────────────────────────────────────────────────┤
│  ComposableHeuristics      │  RecoveryState                │
│  • Custom EcommerceHeuristics  │  • Checkpoint tracking    │
│  • Common hints (add_to_cart)  │  • URL-based rollback     │
├─────────────────────────────────────────────────────────────┤
│                    CaptchaConfig                           │
│  • abort: fail fast        │  • human: manual solve        │
│  • external: 2Captcha/etc  │  • custom handler             │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

```bash
# Install SDK from local path
pip install -e ../../sdk-python

# Install other dependencies
pip install -r requirements.txt

# For OpenAI models (default)
export OPENAI_API_KEY=sk-...

# For local MLX models (Apple Silicon)
pip install mlx-lm

# For local HuggingFace models
pip install torch transformers
```

### Usage Commands

#### Default Search Task (OpenAI)

Searches for "laptop" on Amazon, clicks first product, adds to cart, proceeds to checkout:

```bash
python main.py
```

**Starting URL**: `https://www.amazon.com`

#### Local LLM Models

Use `--local` flag to switch from OpenAI to local models:

```bash
# Default local models (MLX on Apple Silicon)
# Planner: mlx-community/Qwen3-8B-4bit
# Executor: mlx-community/Qwen3-4B-4bit
python main.py --local

# Custom local models
python main.py --local --planner-model mlx-community/Qwen3-8B-4bit --executor-model mlx-community/Qwen3-4B-4bit

# Use HuggingFace transformers instead of MLX
python main.py --local --provider hf --planner-model Qwen/Qwen2.5-7B-Instruct --executor-model Qwen/Qwen2.5-3B-Instruct
```

#### Custom Search Query

```bash
# Search for a specific product
python main.py --query "wireless mouse"

# Or via environment variable
AMAZON_QUERY="thinkpad laptop" python main.py

# With local models
python main.py --local --query "thinkpad laptop"
```

**Starting URL**: `https://www.amazon.com`

#### High-Level Goal (Less Defined Task)

When you provide a `--goal`, the planner generates steps to achieve it. The browser still starts at Amazon:

```bash
# With OpenAI
python main.py --goal "Find a good deal on headphones and add to cart"

# With local models
python main.py --local --goal "Find a good deal on headphones and add to cart"
```

**Starting URL**: `https://www.amazon.com` (default, can be changed in code)

The planner will:
1. Parse the high-level goal
2. Generate appropriate steps (navigate, search, click, etc.)
3. Include verification predicates for each step
4. Execute and verify each step

#### CAPTCHA Handling

```bash
# Abort on CAPTCHA (default)
python main.py

# Human handoff - waits for you to solve CAPTCHA manually
CAPTCHA_MODE=human python main.py

# External solver integration (requires API key in code)
CAPTCHA_MODE=external python main.py
```

#### Headless Mode

```bash
# Run without visible browser window
python main.py --headless

# Or via environment variable
HEADLESS=true python main.py
```

#### Debug Mode

```bash
# Enable verbose logging
DEBUG=true python main.py
```

#### Combined Examples

```bash
# Local models with human CAPTCHA solving
CAPTCHA_MODE=human python main.py --local --query "keyboard"

# Local models with high-level goal and debug logging
DEBUG=true python main.py --local --goal "Find the cheapest laptop under $500"

# OpenAI with custom models
PLANNER_MODEL=gpt-4-turbo EXECUTOR_MODEL=gpt-3.5-turbo python main.py

# Local HuggingFace models with headless mode
python main.py --local --provider hf --headless
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required for OpenAI) | OpenAI API key |
| `PLANNER_MODEL` | `gpt-4o` / `mlx-community/Qwen3-8B-4bit` | Model for planning |
| `EXECUTOR_MODEL` | `gpt-4o-mini` / `mlx-community/Qwen3-4B-4bit` | Model for execution |
| `CAPTCHA_MODE` | `abort` | `abort`, `human`, or `external` |
| `AMAZON_QUERY` | `laptop` | Default search query |
| `HEADLESS` | `false` | Run browser headless |
| `DEBUG` | `false` | Enable debug logging |

### Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--goal "..."` | High-level goal for the planner (less defined task) |
| `--query "..."` | Specific search query (overrides `AMAZON_QUERY`) |
| `--headless` | Run browser in headless mode |
| `--local` | Use local LLM models instead of OpenAI |
| `--provider {mlx,hf}` | Local model provider: `mlx` (Apple Silicon) or `hf` (HuggingFace) |
| `--planner-model "..."` | Override planner model name |
| `--executor-model "..."` | Override executor model name |

### Website Navigation

**All modes start at `https://www.amazon.com`** by default:

| Mode | Starting URL | Task Generation |
|------|--------------|-----------------|
| Default | `https://www.amazon.com` | Search for `AMAZON_QUERY`, add to cart, checkout |
| `--query` | `https://www.amazon.com` | Search for specified query, add to cart, checkout |
| `--goal` | `https://www.amazon.com` | Planner generates steps based on goal |

To use a different website, modify `starting_url` in `create_automation_task()` in `main.py`.

## AutomationTask vs WebBenchTask

The SDK's `AutomationTask` abstracts `WebBenchTask` for general-purpose automation:

```python
# Old WebBenchTask approach (specific to webbench)
task = WebBenchTask(
    id="task-001",
    starting_url="https://amazon.com",
    task="Search for laptop",
    category="CREATE",  # WebBench-specific category
)

# New AutomationTask approach (SDK abstraction)
task = AutomationTask(
    task_id="purchase-laptop",
    starting_url="https://amazon.com",
    task="Find a laptop under $1000 and add to cart",
    category=TaskCategory.TRANSACTION,  # Generic category
    enable_recovery=True,
    max_recovery_attempts=2,
)

# Add success criteria
task = task.with_success_criteria(
    {"predicate": "url_contains", "args": ["/cart"]},
    {"predicate": "exists", "args": [".cart-item"]},
)
```

## CAPTCHA Handling

### Abort Mode (Default)

Fails immediately when CAPTCHA is detected:

```bash
CAPTCHA_MODE=abort python main.py
```

### Human Handoff

Waits for manual CAPTCHA solve:

```bash
CAPTCHA_MODE=human python main.py
```

When a CAPTCHA appears, solve it in the browser window within 3 minutes.

### External Solver

Integrate with services like 2Captcha or CapSolver:

```bash
CAPTCHA_MODE=external python main.py
```

For production use, modify the `external_solver` function in `main.py`:

```python
def external_solver(ctx: CaptchaContext) -> bool:
    from twocaptcha import TwoCaptcha
    solver = TwoCaptcha('YOUR_API_KEY')

    if ctx.captcha.type == "recaptcha":
        result = solver.recaptcha(
            sitekey=ctx.captcha.sitekey,
            url=ctx.url,
        )
        # Inject solution...
    return True
```

## Custom Heuristics

The demo includes `EcommerceHeuristics` for Amazon-specific element selection:

```python
class EcommerceHeuristics:
    def find_element_for_intent(self, intent, elements, url, goal):
        if "add" in intent and "cart" in intent:
            return self._find_add_to_cart(elements)
        if "checkout" in intent:
            return self._find_checkout_button(elements)
        # ...
        return None  # Fall back to LLM
```

This allows element selection without LLM calls for common patterns:
- Search box detection
- Add to Cart button
- Checkout/Proceed button
- First product link (matches "Click on product title", "first product link", etc.)
- Modal dismiss buttons
- Cookie consent

## High-Level Goals

The planner handles less-defined tasks by generating appropriate steps. When you use `--goal`, the task description is passed directly to the planner without a pre-defined step template:

```bash
# The planner will figure out what steps are needed
python main.py --goal "Find a good laptop deal and add to cart"

# More specific goal
python main.py --goal "Search for wireless earbuds under $50 with good reviews"

# Complex multi-step goal
python main.py --goal "Find a ThinkPad laptop, check the reviews, and add to cart if rating is above 4 stars"
```

**How it works:**

1. The `AutomationTask` is created with only the high-level goal (no predefined steps)
2. The planner LLM (gpt-4o) analyzes the goal and current page
3. It generates a JSON plan with steps like:
   - NAVIGATE to search
   - CLICK search box
   - TYPE_AND_SUBMIT query
   - CLICK product link
   - CLICK add to cart
4. Each step includes verification predicates
5. The executor runs each step with heuristics or LLM fallback
6. If steps fail, the planner replans

**Example generated plan for "Find a good laptop deal":**
```json
{
  "task": "Find a good laptop deal and add to cart",
  "steps": [
    {"id": 1, "goal": "Click search box", "action": "CLICK", "intent": "search_box"},
    {"id": 2, "goal": "Search for laptop", "action": "TYPE_AND_SUBMIT", "input": "laptop deals"},
    {"id": 3, "goal": "Click first product", "action": "CLICK", "intent": "first_product_link"},
    {"id": 4, "goal": "Add to cart", "action": "CLICK", "intent": "add_to_cart"}
  ]
}
```

## Recovery and Rollback

When enabled, the agent:
1. Creates checkpoints after each successful step
2. On failure, attempts recovery to the last checkpoint
3. Re-verifies page state and resumes

```python
task = AutomationTask(
    task_id="...",
    starting_url="...",
    task="...",
    enable_recovery=True,
    max_recovery_attempts=2,
)
```

## Auth Boundary Detection

The agent automatically detects authentication boundaries (login/signin pages) and stops gracefully instead of attempting to log in or getting stuck:

```python
from predicate.agents.planner_executor_agent import AuthBoundaryConfig

# Configure auth boundary detection
auth_config = AuthBoundaryConfig(
    enabled=True,
    url_patterns=["/signin", "/login", "/auth", "/account/login"],
    element_patterns=["sign in", "log in", "username", "password"],
)

result = await agent.run(
    task=task,
    auth_boundary_config=auth_config,
)

# Check if auth boundary was hit
if result.auth_boundary_hit:
    print(f"Stopped at auth page: {result.auth_boundary_url}")
```

**Default behavior:**
- Detects URLs containing `/signin`, `/login`, `/auth`, etc.
- Detects form elements with signin/login labels
- Marks task as successful up to the auth boundary
- Reports which step hit the boundary

## Scroll-After-Escalation

When an element isn't found even after limit escalation, the agent can scroll the page to find off-screen elements:

```python
from predicate.agents.planner_executor_agent import SnapshotEscalationConfig

# Configure snapshot escalation with scrolling
escalation_config = SnapshotEscalationConfig(
    enabled=True,
    initial_limit=50,
    max_limit=200,

    # Scroll configuration (viewport-adaptive)
    scroll_after_escalation=True,
    scroll_viewport_fraction=0.4,  # Scroll by 40% of viewport height
    scroll_max_attempts=3,
    scroll_directions=["down", "up"],
)

result = await agent.run(
    task=task,
    snapshot_escalation_config=escalation_config,
)
```

**Key parameters:**
- `scroll_viewport_fraction`: Fraction of viewport height to scroll (default: 0.4 = 40%)
- `scroll_max_attempts`: Maximum scroll attempts per direction (default: 3)
- `scroll_directions`: Which directions to try (default: `["down", "up"]`)

**How it works:**
1. Initial element search with `initial_limit` elements
2. If not found, escalate to `max_limit` elements
3. If still not found and `scroll_after_escalation=True`:
   - Scroll down by `viewport_height * scroll_viewport_fraction`
   - Re-capture snapshot and search again
   - Repeat up to `scroll_max_attempts` times
   - Try opposite direction if needed
4. Adaptive scrolling prevents overshooting (uses viewport-relative distance)

## Comparison with planner_executor_local

| Feature | planner_executor_local | planner_executor_local2 (this demo) |
|---------|------------------------|-------------------------------------|
| Implementation | From scratch | SDK's PlannerExecutorAgent |
| Task model | Custom | AutomationTask |
| CAPTCHA | Manual integration | CaptchaConfig |
| Recovery | Custom | RecoveryState |
| Heuristics | Inline functions | EcommerceHeuristics + SDK |
| Modals | Manual detection | ComposableHeuristics |
| OpenAI models | Yes | Yes (default) |
| Local models | HuggingFace/MLX | Yes (`--local` flag) |

## Local LLM Models

### MLX (Apple Silicon - Recommended)

MLX provides efficient inference on M1/M2/M3/M4 Macs:

```bash
# Install mlx-lm
pip install mlx-lm

# Run with default local models
python main.py --local

# Default models:
# - Planner: mlx-community/Qwen3-8B-4bit (9B params, 4-bit quantized)
# - Executor: mlx-community/Qwen3-4B-4bit (4B params, 4-bit quantized)
```

### HuggingFace Transformers

For CUDA GPUs or CPU inference:

```bash
# Install dependencies
pip install torch transformers

# Run with HuggingFace provider
python main.py --local --provider hf

# Custom models
python main.py --local --provider hf \
    --planner-model Qwen/Qwen2.5-7B-Instruct \
    --executor-model Qwen/Qwen2.5-3B-Instruct
```

### Model Requirements

| Role | Recommended Size | Purpose |
|------|------------------|---------|
| Planner | 7B-9B params | JSON plan generation, verification predicates |
| Executor | 3B-4B params | Element selection, action execution |

Smaller executor models reduce latency per step while maintaining accuracy.

## Files

| File | Description |
|------|-------------|
| `main.py` | Main demo script |
| `requirements.txt` | Python dependencies |
| `traces/` | Trace files for visualization |

## Troubleshooting

### CAPTCHA Detection

If CAPTCHA is detected unexpectedly:
- Use `CAPTCHA_MODE=human` for manual solving
- Check if IP is flagged (use VPN/proxy)
- Reduce automation speed

### Element Not Found

If elements are not found:
- Increase snapshot limits in `SnapshotEscalationConfig`
- Enable `scroll_after_escalation=True` for off-screen elements
- Adjust `scroll_viewport_fraction` (smaller = finer scrolling)
- Add custom heuristics for the site
- Check if page requires vision fallback

### Recovery Failures

If recovery fails repeatedly:
- Check if URLs are bookmarkable
- Verify checkpoint predicates are stable
- Increase `max_recovery_attempts`

## Documentation

See the full SDK documentation:
- [PlannerExecutorAgent User Manual](../../sdk-python/docs/PLANNER_EXECUTOR_AGENT.md)
- [AutomationTask Design](../../docs/sdk-python-doc/automation-task-design.md)
