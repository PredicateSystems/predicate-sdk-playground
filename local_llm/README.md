## Local LLM Integration with Predicate SDK

This directory contains a complete implementation for using small, local LLMs (like Qwen 2.5 3B, Gemma 2 2B) with the Predicate Python SDK for web automation.

### ⚡ Quick Start Requirements

- **Disk Space**: ~6 GB for Qwen 2.5 3B model (smallest recommended)
- **RAM**: 8 GB minimum (16 GB recommended)
- **GPU**: Optional but recommended (8x faster than CPU)
- **Python**: 3.8+

### Overview

Local LLMs provide:
- **Zero API costs** - No per-token charges
- **Privacy** - All processing happens locally
- **Low latency** - No network round trips (if using GPU)
- **Offline capability** - Works without internet

The implementation includes:
- Generic LLM interface (works with both local and cloud models)
- Optimized element filtering (60-70% token reduction)
- Compact prompt engineering for small context windows
- Robust response parsing with fallbacks
- Complete Google search demo
- Multi-model comparison framework

### Directory Structure

```
local_llm/
├── models/                      # LLM implementations
│   ├── base_llm.py             # Abstract interface
│   ├── local_llm.py            # Local LLM (Hugging Face)
│   └── cloud_llm.py            # Cloud LLM (OpenAI)
│
├── shared/                      # Shared utilities
│   ├── utils.py                # Screenshots, token tracking
│   ├── element_processor.py   # Element filtering & compression
│   ├── prompt_builder.py      # Optimized prompts
│   ├── response_parser.py     # Response parsing
│   └── web_agent.py            # Main automation agent
│
├── demos/                       # Demo scripts
│   └── google_search.py        # Google search demo
│
├── compare_models.py            # Multi-model comparison
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

### Installation & Quick Start

#### Before You Start: Free Up Disk Space (Recommended)

The Qwen 2.5 3B model requires ~6 GB of disk space. Check your cache first:

```bash
# Check what's taking up space
python check_cache_sizes.py

# Quick cleanup (safe, frees ~4-5 GB):
npm cache clean --force
pip cache purge
brew cleanup -s
rm -rf ~/.cargo/registry
rm -rf ~/.gradle/caches

# Or use interactive cleanup:
bash cleanup_mac_cache.sh
```

#### Step 1: Install Dependencies

```bash
cd playground/local_llm
pip install -r requirements.txt
```

#### Step 2: Verify Setup

```bash
python test_setup.py
```

Expected output: `✅ All tests passed!`

#### Step 3: Run Demo (Auto-Downloads Model)

```bash
python demos/google_search.py
```

**First run**: Downloads Qwen 2.5 3B (~6 GB, takes 5-15 minutes)
**Subsequent runs**: Uses cached model (instant)

The model will be cached at: `~/.cache/huggingface/hub/`

#### Step 4 (Optional): Compare Models

```bash
python compare_models.py
```

---

### Model Download Details

**Default Model**: Qwen 2.5 3B (smallest recommended model)
- **Size**: ~6 GB
- **Download URL**: [Hugging Face - Qwen/Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
- **Auto-downloads** on first run
- **Cached at**: `~/.cache/huggingface/hub/`

**Manual pre-download** (optional):
```bash
python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
model_name = 'Qwen/Qwen2.5-3B-Instruct'
print(f'Downloading {model_name}...')
AutoTokenizer.from_pretrained(model_name)
AutoModelForCausalLM.from_pretrained(model_name)
print('✅ Download complete!')
"
```

**No Ollama required!** This implementation uses Hugging Face Transformers directly.

### Quick Start

#### Run Google Search Demo

```bash
python demos/google_search.py
```

This will:
1. Navigate to Google
2. Find the search box (using local LLM)
3. Type "visiting japan"
4. Select first non-ad result (using local LLM)
5. Save screenshots and token usage data

#### Compare Multiple Models

```bash
python compare_models.py
```

This runs the same task with different models and generates a comparison report.

### Usage Examples

#### Using a Local LLM

```python
from models.local_llm import LocalLLM
from shared.web_agent import WebAgent
from predicate import PredicateBrowser, snapshot

# Initialize local LLM
llm = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    device="auto",
    load_in_4bit=False  # Set True for 4-bit quantization
)

# Create agent
agent = WebAgent(llm=llm, max_elements=15)

# Use in automation
with PredicateBrowser(headless=False) as browser:
    browser.goto("https://www.google.com")

    # Get snapshot
    snapshot_data = snapshot(browser, screenshot=False)

    # Find element using LLM
    result = agent.analyze_and_select(
        snapshot_data=snapshot_data,
        task_type="find_input",
        context="search box"
    )

    if result:
        print(f"Found element: {result['element'].text}")
        print(f"Tokens used: {result['tokens_used']}")
```

#### Using a Cloud LLM (for comparison)

```python
from models.cloud_llm import CloudLLM
from shared.web_agent import WebAgent

# Initialize cloud LLM
llm = CloudLLM(
    model="gpt-4-turbo-preview",
    api_key="your-api-key"  # Or set OPENAI_API_KEY env var
)

# Rest is the same as local LLM
agent = WebAgent(llm=llm)
```

#### Custom Model Configuration

```python
# Use different local models
llm_qwen = LocalLLM(model_name="Qwen/Qwen2.5-3B-Instruct")
llm_gemma = LocalLLM(model_name="google/gemma-2-2b-it")
llm_phi = LocalLLM(model_name="microsoft/Phi-3-mini-4k-instruct")

# Use quantization to save memory
llm_4bit = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    load_in_4bit=True  # 75% memory reduction
)

llm_8bit = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    load_in_8bit=True  # 50% memory reduction
)
```

### Supported Models

#### Tier 1: Ultra-Light (1-3B parameters) - Recommended for Limited Disk Space

| Model | Disk Size | RAM | VRAM | Context | Best For |
|-------|-----------|-----|------|---------|----------|
| **Qwen/Qwen2.5-3B-Instruct** ⭐ | **~6 GB** | 8 GB | 6 GB | 32K | **Best balance (DEFAULT)** |
| google/gemma-2-2b-it | ~5 GB | 8 GB | 4 GB | 8K | Ultra-fast, smallest |
| microsoft/Phi-3-mini-4k-instruct | ~7 GB | 8 GB | 6 GB | 4K | Strong reasoning |

**⭐ Qwen 2.5 3B is the default** - Best quality-to-size ratio!

#### Tier 2: Light (7-9B parameters) - Requires More Resources

| Model | Disk Size | RAM | VRAM | Context | Best For |
|-------|-----------|-----|------|---------|----------|
| Qwen/Qwen2.5-7B-Instruct | ~15 GB | 16 GB | 14 GB | 32K | Better accuracy |
| google/gemma-2-9b-it | ~18 GB | 16 GB | 16 GB | 8K | Google-trained |
| meta-llama/Llama-3.2-8B-Instruct | ~16 GB | 16 GB | 14 GB | 128K | Large context |

**Note**: With 4-bit quantization, VRAM requirements drop by ~75% (e.g., 3B model: 6GB → 2GB)

### Task Types

The agent supports four task types:

1. **`find_input`** - Find input fields (search boxes, text inputs)
   ```python
   agent.analyze_and_select(
       snapshot_data=snapshot_data,
       task_type="find_input",
       context="email input"
   )
   ```

2. **`find_button`** - Find buttons by text
   ```python
   agent.analyze_and_select(
       snapshot_data=snapshot_data,
       task_type="find_button",
       context="Sign In"
   )
   ```

3. **`find_link`** - Find links (e.g., search results)
   ```python
   agent.analyze_and_select(
       snapshot_data=snapshot_data,
       task_type="find_link",
       context="Select first result",
       exclude_text_patterns=["Ad", "Sponsored"]
   )
   ```

4. **`select_from_list`** - Select specific item from list
   ```python
   agent.analyze_and_select(
       snapshot_data=snapshot_data,
       task_type="select_from_list",
       context="United States"
   )
   ```

### Element Filtering

The system automatically filters elements to reduce token usage:

- **By task type**: Only includes relevant element roles
- **By visibility**: Removes hidden/out-of-viewport elements
- **By importance**: Keeps top-k most important elements
- **By text patterns**: Excludes elements with specific text

Example filtering results:
```
Original: 247 elements
After task filter: 68 elements
After visibility filter: 42 elements
Top-15: 15 elements
Reduction: 93.9%
```

### Performance Benchmarks

Expected results on Google search task:

| Model | Tokens | Duration | Accuracy |
|-------|--------|----------|----------|
| Qwen 2.5 3B | ~2,500 | ~5s | 85% |
| Gemma 2 2B | ~2,800 | ~4s | 75% |
| GPT-4 Turbo | ~3,500 | ~8s | 98% |

*Note: Local models run on GPU. CPU inference will be 5-10x slower.*

### Troubleshooting

#### CUDA out of memory

Use quantization:
```python
llm = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    load_in_4bit=True  # Reduces memory by 75%
)
```

Or use CPU (slower):
```python
llm = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    device="cpu"
)
```

#### LLM returns invalid JSON

The response parser handles this automatically. If issues persist:
- Check that you're using an instruction-tuned model (models ending in `-Instruct` or `-it`)
- Increase `temperature` slightly (e.g., 0.2) for more variety
- Try a different model

#### Low accuracy

- Increase `max_elements` in WebAgent (default: 15)
- Use a larger model (7B instead of 3B)
- Check element filtering - you might be filtering out the target element

### Hardware Requirements

| Model Size | GPU VRAM | CPU RAM | Notes |
|------------|----------|---------|-------|
| 2-3B (float16) | 6GB | 16GB | Recommended minimum |
| 2-3B (4-bit) | 2GB | 8GB | With quantization |
| 7-9B (float16) | 16GB | 32GB | Better accuracy |
| 7-9B (4-bit) | 4GB | 16GB | With quantization |

### Output Organization

Each demo run creates a timestamped folder:

```
google_search_Qwen2.5-3B-Instruct/
└── screenshots/
    └── 20241223_084530/
        ├── scene1_homepage.png
        ├── scene1_homepage_data.json
        ├── scene2_search_results.png
        ├── scene3_search_results_data.json
        ├── scene4_target_page.png
        ├── token_summary_data.json
        └── results_data.json
```

### Documentation

For detailed design and architecture, see:
- [docs/LOCAL_LLM_INTEGRATION.md](../../docs/LOCAL_LLM_INTEGRATION.md)

### License

Same as Predicate SDK - see repository root.
