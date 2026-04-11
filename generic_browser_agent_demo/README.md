# Generic Browser Agent Demo

A modular demo showcasing the Predicate SDK's `PlannerExecutorAgent` for browser automation across diverse task categories.

## Key Features

- **Multi-Provider Support**: OpenAI, DeepInfra, Ollama, MLX (Apple Silicon), HuggingFace
- **Semantic Snapshots**: 10x more token-efficient than vision-based approaches
- **Pre-built Task Templates**: Shopping, search, forms, travel, social media
- **Domain Heuristics**: Fast element selection without LLM calls for common patterns
- **Automatic Overlay Handling**: Proactive dismissal of cookie consent, newsletter popups, modal dialogs before agent execution
- **Recovery & Replan**: Automatic recovery from failures with intelligent replanning

## Architecture

The demo uses a **Planner + Executor** architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Task                               │
│  "Search for laptop on Amazon and add to cart"                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PLANNER (7B+ model)                        │
│  - Generates JSON execution plan                                │
│  - Defines steps with goals, actions, verification             │
│  - Handles cookie consent, popups, overlays                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXECUTOR (3B-7B model)                      │
│  - Receives semantic DOM snapshot (not screenshots)             │
│  - Selects element ID for each action                          │
│  - Falls back to vision model if needed                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VERIFICATION LOOP                            │
│  - Executes action on page                                     │
│  - Verifies predicates (url_contains, exists, etc.)            │
│  - Replans on failure                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Navigate to the demo directory
cd sentience-sdk-playground/generic_browser_agent_demo

# Install dependencies
pip install -r requirements.txt

# Install the SDK (from local path)
pip install -e ../../sdk-python
```

---

## Usage Examples

### Example 1: E-Commerce Shopping with OpenAI

Complete a shopping flow on Amazon using GPT-4o for planning and GPT-4o-mini for execution.

```bash
export OPENAI_API_KEY="sk-..."

python main.py \
  --task "Search for 'wireless mouse', click the first product, and add it to cart" \
  --url https://www.amazon.com \
  --verbose
```

**What happens:**
1. Planner generates a multi-step plan: navigate → search → click product → add to cart
2. Each step includes verification predicates (e.g., `url_contains("/dp/")`)
3. Executor identifies elements using semantic snapshots
4. Cookie consent and popups are automatically dismissed

---

### Example 2: Using DeepInfra with Qwen Models

Run the same task with Qwen 27B (planner) and Qwen 9B (executor) via DeepInfra API.

```bash
export DEEPINFRA_API_KEY="..."

python main.py \
  --provider deepinfra \
  --task "Search for 'Rainbow Trout Trucker' hat, select a size, add to cart, proceed to checkout" \
  --url https://www.lifeisgood.com \
  --verbose
```

**Key insight:** DeepInfra provides access to powerful open-source models at lower cost than OpenAI, while maintaining high quality for browser automation tasks.

---

### Example 3: Fully Local with Ollama

Run entirely locally using Ollama - no API keys needed, complete privacy.

```bash
# First, pull the models
ollama pull qwen2.5:14b
ollama pull qwen2.5:7b

# Run the demo
python main.py \
  --provider ollama \
  --planner-model qwen2.5:14b \
  --executor-model qwen2.5:7b \
  --task "Extract the top 5 story titles from Hacker News" \
  --url https://news.ycombinator.com \
  --category read
```

**Output example:**
```
Steps completed: 3/3
Duration: 12450ms
Final URL: https://news.ycombinator.com/
Extracted: ["Story 1 title", "Story 2 title", ...]
```

---

### Example 4: Apple Silicon Optimized (MLX)

Use MLX-optimized models on M1/M2/M3/M4 Macs for fast local inference.

```bash
# Install MLX
pip install mlx-lm

# Run with MLX (models auto-download from HuggingFace)
python main.py \
  --provider mlx \
  --planner-model mlx-community/Qwen3-8B-4bit \
  --executor-model mlx-community/Qwen3-4B-4bit \
  --task "Search Wikipedia for 'Artificial Intelligence' and extract the first paragraph" \
  --url https://en.wikipedia.org
```

**Performance:** MLX models run at ~30-50 tokens/sec on M2 Pro, making local automation practical.

---

### Example 5: Using Pre-defined Task Templates

Skip writing task descriptions - use built-in templates for common scenarios.

```bash
# List all available templates
python main.py --list-templates

# Run the Life Is Good shopping template
python main.py --template lifeisgood_shopping --provider deepinfra

# Run Amazon shopping template
python main.py --template amazon_search_add_to_cart

# Run news extraction template
python main.py --template news_headlines --provider ollama
```

**Available templates:**
- `amazon_search_add_to_cart` - Complete Amazon shopping flow
- `lifeisgood_shopping` - Life Is Good e-commerce checkout
- `bestbuy_product_search` - Search BestBuy for products
- `wikipedia_extract` - Extract Wikipedia article content
- `news_headlines` - Extract Hacker News headlines
- `recipe_search` - Search AllRecipes
- `github_repo_info` - Extract GitHub repository info

---

### Example 6: Mixed Provider Configuration

Use a cloud model for planning (better reasoning) and local model for execution (faster, cheaper).

```bash
# Cloud planner + local executor
python main.py \
  --planner-provider openai \
  --planner-model gpt-4o \
  --executor-provider ollama \
  --executor-model qwen2.5:7b \
  --task "Find the price of iPhone 15 Pro on Apple.com" \
  --url https://www.apple.com
```

---

### Example 7: Headless Mode for CI/CD

Run in headless mode for automated testing or CI pipelines.

```bash
python main.py \
  --headless \
  --json-output \
  --provider deepinfra \
  --task "Verify the login page loads correctly" \
  --url https://example.com/login
```

**JSON output:**
```json
{
  "success": true,
  "task_id": "read-20260407-191234",
  "steps_completed": 2,
  "steps_total": 2,
  "duration_ms": 5420,
  "token_usage": {
    "total": {"total_tokens": 1847}
  }
}
```

---

### Example 8: Verbose Mode for Debugging

See the full plan and executor prompts for debugging.

```bash
DEBUG=1 python main.py \
  --verbose \
  --task "Click the Sign In button" \
  --url https://github.com
```

**Verbose output includes:**
- Generated JSON plan with all steps
- Executor prompts with element context
- Verification predicate results
- Token usage breakdown

---

## CLI Reference

### Task Options

| Option | Description |
|--------|-------------|
| `--task TEXT` | Natural language task description |
| `--url URL` | Starting URL for automation |
| `--template NAME` | Use a pre-defined task template |
| `--list-templates` | List all available templates |
| `--category TYPE` | Task category: read, create, update, delete, transaction |

### Provider Options

| Option | Description |
|--------|-------------|
| `--provider TYPE` | LLM backend: openai, deepinfra, ollama, mlx, huggingface |
| `--planner-model NAME` | Override planner model |
| `--executor-model NAME` | Override executor model |
| `--planner-provider TYPE` | Use different provider for planner |
| `--executor-provider TYPE` | Use different provider for executor |

### Agent Options

| Option | Description |
|--------|-------------|
| `--max-steps N` | Maximum steps before giving up (default: 30) |
| `--max-replans N` | Maximum replans on failure (default: 2) |
| `--stepwise` | Use ReAct-style stepwise planning |
| `--verbose` | Print prompts and plans to stdout |

### Browser Options

| Option | Description |
|--------|-------------|
| `--headless` | Run browser in headless mode |
| `--no-headless` | Force visible browser |

### Output Options

| Option | Description |
|--------|-------------|
| `--out-dir PATH` | Output directory for artifacts (default: runs) |
| `--json-output` | Output result as JSON |

---

## Task Templates

The demo includes pre-defined templates for common automation scenarios:

### Shopping (TRANSACTION)
- `amazon_search_add_to_cart` - Search and add to cart on Amazon
- `lifeisgood_shopping` - Complete shopping flow on lifeisgood.com
- `bestbuy_product_search` - Search products on BestBuy

### Information Extraction (READ)
- `wikipedia_extract` - Extract article content from Wikipedia
- `news_headlines` - Extract Hacker News headlines
- `recipe_search` - Search recipes on AllRecipes
- `weather_lookup` - Get weather forecast

### Forms (CREATE)
- `contact_form` - Fill out a contact form
- `newsletter_signup` - Subscribe to newsletter

### Travel (READ)
- `flight_search` - Search flights on Google Flights
- `hotel_search` - Search hotels on Booking.com

### Social/Developer (READ)
- `github_repo_info` - Extract repo info from GitHub
- `reddit_search` - Search and extract Reddit posts

List all templates:
```bash
python main.py --list-templates
```

---

## Project Structure

```
generic_browser_agent_demo/
├── main.py              # Entry point with CLI
├── task_definitions.py  # Task templates and factory
├── providers.py         # LLM provider factory
├── heuristics.py        # Domain-specific element heuristics
├── overlay_utils.py     # Proactive overlay/modal dismissal
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

---

## Module Documentation

### task_definitions.py

Defines `TaskDefinition` dataclass and pre-built templates:

```python
from task_definitions import create_custom_task, TaskCategory

# Create a custom task
task = create_custom_task(
    starting_url="https://mysite.com",
    task="Find pricing page and extract all plan prices",
    category=TaskCategory.READ,
    domain_hints=("saas",),
)
```

### providers.py

Factory for creating LLM providers:

```python
from providers import create_planner_executor_providers

# Create providers for a specific mode
planner, executor = create_planner_executor_providers(
    mode="deepinfra",
    planner_model="Qwen/Qwen3.5-27B",
    executor_model="Qwen/Qwen3.5-9B",
)
```

### heuristics.py

Domain-specific heuristics for faster element selection:

```python
from heuristics import EcommerceHeuristics, get_heuristics_for_domain

# Get heuristics for e-commerce
heuristics = get_heuristics_for_domain(("ecommerce", "amazon"))

# Use in agent
agent = PlannerExecutorAgent(
    planner=planner,
    executor=executor,
    intent_heuristics=heuristics,
)
```

### overlay_utils.py

Proactive overlay/modal dismissal to clear blocking elements before the agent runs:

```python
from overlay_utils import dismiss_overlays_before_agent

# After page load, before agent run:
result = await dismiss_overlays_before_agent(runtime, browser, verbose=True)

# Result includes:
# - actions: List of actions taken (e.g., 'PRESS("Escape")', 'OVERLAY_CLICK("Accept")')
# - overlays_before: Count of overlays detected initially
# - overlays_after: Count of overlays remaining
# - status: "gone", "partial", "no_candidates", "timeout", or "none"
```

The overlay dismissal handles:
- Cookie consent banners
- Newsletter signup popups
- Promotional overlays
- Product protection upsells
- GDPR/privacy dialogs

Detection methods:
- Gateway modal detection (`modal_detected`, `modal_grids`)
- ARIA roles (`dialog`, `alertdialog`)
- Class name patterns (`modal`, `overlay`, `popup`, `cookie`, etc.)
- Z-index analysis (elements with z-index >= 1000)

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for OpenAI provider |
| `DEEPINFRA_API_KEY` | Required for DeepInfra provider |
| `PREDICATE_API_KEY` | Optional: enables cloud overlay and tracing |
| `DEBUG` | Set to "1" for verbose logging |

---

## Token Efficiency

The semantic snapshot approach is highly token-efficient compared to vision-based methods:

| Approach | Tokens per Step | 10-Step Task |
|----------|-----------------|--------------|
| Vision (screenshots) | 2,000-3,000 | 20,000-30,000 |
| Semantic Snapshots | 200-400 | 2,000-4,000 |

The executor sees compact element representations like:
```
[4128] <button> "Accept" {CLICKABLE} @ (640,450) importance:892
[105] <textbox> "Search" {CLICKABLE} @ (400,60) importance:756
[2341] <button> "Add to Cart" {PRIMARY,CLICKABLE} @ (320,580) importance:945
```

**Why this matters:**
- 10x fewer tokens = 10x lower cost
- Faster inference (less data to process)
- Works with smaller models (4B-7B parameters)
- No image processing overhead

---

## Troubleshooting

### "OPENAI_API_KEY not set"
Set the environment variable or use a different provider:
```bash
export OPENAI_API_KEY="sk-..."
# or
python main.py --provider ollama --task "..."
```

### "DEEPINFRA_API_KEY not set"
Get an API key from [DeepInfra](https://deepinfra.com):
```bash
export DEEPINFRA_API_KEY="..."
```

### "Ollama connection refused"
Make sure Ollama is running:
```bash
ollama serve
```

### "MLX not available"
Install mlx-lm (Apple Silicon only):
```bash
pip install mlx-lm
```

### Browser doesn't open
Try without headless mode:
```bash
python main.py --no-headless --task "..."
```

### Task fails with "element not found"
Try with verbose mode to debug:
```bash
python main.py --verbose --task "..." --url "..."
```

---

## License

MIT License - see the SDK repository for details.
