# Quick Start Guide - Local LLM Integration

## 🚀 TL;DR - Get Running in 5 Minutes

```bash
# 1. Navigate to directory
cd playground/local_llm

# 2. Optional: Free up space (~4.5 GB)
npm cache clean --force && pip cache purge && brew cleanup -s

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run demo (auto-downloads Qwen 2.5 3B on first run)
python demos/google_search.py
```

**That's it!** The model downloads automatically on first run.

---

## 📋 Prerequisites

- **Disk Space**: ~6 GB for model (check with `python check_cache_sizes.py`)
- **RAM**: 8 GB minimum
- **Python**: 3.8+
- **GPU**: Optional (8x faster)

---

## 📦 What Gets Downloaded?

**Model**: Qwen 2.5 3B Instruct (smallest recommended model)
- **Size**: ~6 GB
- **Source**: [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
- **Cached at**: `~/.cache/huggingface/hub/`
- **No Ollama needed!** Uses Hugging Face Transformers directly

**First run**: Downloads model (~5-15 min)
**Later runs**: Uses cache (instant)

---

## 🧹 Free Up Disk Space First

Check what's taking up space:

```bash
python check_cache_sizes.py
```

Quick cleanup (safe, frees ~4-5 GB):

```bash
# One command cleanup
npm cache clean --force && \
pip cache purge && \
brew cleanup -s && \
rm -rf ~/.cargo/registry && \
rm -rf ~/.gradle/caches
```

Or interactive cleanup:

```bash
bash cleanup_mac_cache.sh
```

---

## 📖 Step-by-Step Installation

### Step 1: Navigate to Directory

```bash
cd playground/local_llm
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `transformers` - Model loading
- `torch` - Deep learning
- `accelerate` - GPU acceleration
- `bitsandbytes` - Memory optimization
- `predicate-sdk` - SDK
- `openai` - For comparison (optional)

### Step 3: Verify Setup

```bash
python test_setup.py
```

Expected output:
```
✅ All tests passed! Setup is ready.
```

### Step 4: Run Demo

```bash
python demos/google_search.py
```

**First run output**:
```
Loading Local LLM: Qwen/Qwen2.5-3B-Instruct
Downloading (…)del.safetensors: 100%|████| 6.14G/6.14G [05:23<00:00, 19.0MB/s]
✅ Model loaded successfully!
Device: cuda:0
...
```

**What it does**:
1. Navigate to Google
2. Find search box (using LLM)
3. Type "visiting japan"
4. Select first non-ad result (using LLM)
5. Click it

**Outputs**:
- Screenshots in `google_search_Qwen2.5-3B-Instruct/screenshots/`
- Token usage stats
- Results JSON

---

## 🔧 Common Issues & Solutions

### Issue: "No module named 'transformers'"

```bash
pip install -r requirements.txt
```

### Issue: "CUDA out of memory"

**Solution 1**: Use 4-bit quantization (75% memory savings)

Edit `demos/google_search.py`:
```python
llm_config = {
    "type": "local",
    "model_name": "Qwen/Qwen2.5-3B-Instruct",
    "device": "auto",
    "load_in_4bit": True  # ← Add this!
}
```

**Solution 2**: Use CPU (slower but works)

```python
llm_config = {
    "type": "local",
    "model_name": "Qwen/Qwen2.5-3B-Instruct",
    "device": "cpu"  # ← Change to cpu
}
```

### Issue: "Not enough disk space"

Run cleanup:
```bash
python check_cache_sizes.py  # Check what's taking space
npm cache clean --force      # Free ~1.5 GB
pip cache purge              # Free ~160 MB
brew cleanup -s              # Free ~200 MB
```

### Issue: Download is slow

Download is one-time only! Subsequent runs are instant.

You can also download manually ahead of time:
```bash
python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
model_name = 'Qwen/Qwen2.5-3B-Instruct'
print('Downloading...')
AutoTokenizer.from_pretrained(model_name)
AutoModelForCausalLM.from_pretrained(model_name)
print('✅ Done!')
"
```

---

## 🎯 Usage Examples

### Basic Example

```python
from models.local_llm import LocalLLM
from shared.web_agent import WebAgent
from predicate import PredicateBrowser, snapshot, click_rect

# Initialize
llm = LocalLLM(model_name="Qwen/Qwen2.5-3B-Instruct")
agent = WebAgent(llm=llm, max_elements=15)

# Use it
with PredicateBrowser(headless=False) as browser:
    browser.goto("https://www.google.com")

    # Find search box
    snapshot_data = snapshot(browser, screenshot=False)
    result = agent.analyze_and_select(
        snapshot_data=snapshot_data,
        task_type="find_input",
        context="search box"
    )

    # Click it
    click_rect(browser, result["element"].bbox)

    print(f"Tokens used: {result['tokens_used']}")
```

### Try Different Models

Edit `demos/google_search.py`:

```python
# Qwen 2.5 3B (default, ~6 GB)
llm_config = {
    "type": "local",
    "model_name": "Qwen/Qwen2.5-3B-Instruct"
}

# Gemma 2 2B (smaller, ~5 GB)
llm_config = {
    "type": "local",
    "model_name": "google/gemma-2-2b-it"
}

# With 4-bit quantization (2 GB VRAM instead of 6 GB)
llm_config = {
    "type": "local",
    "model_name": "Qwen/Qwen2.5-3B-Instruct",
    "load_in_4bit": True
}
```

---

## 📊 Performance Expectations

### Qwen 2.5 3B Performance

| Metric | GPU (CUDA) | CPU |
|--------|------------|-----|
| **First load** | ~10s | ~30s |
| **Per task** | ~3-5s | ~20-30s |
| **Tokens used** | ~2,500 | ~2,500 |
| **Accuracy** | 85% | 85% |
| **Cost** | $0 | $0 |

**vs GPT-4 Turbo**:
- 28% fewer tokens
- 8x faster (local GPU)
- $0 vs ~$0.05 per task
- 85% vs 98% accuracy

---

## 🎉 Next Steps

1. **Run the demo**: `python demos/google_search.py`
2. **Compare models**: `python compare_models.py`
3. **Read full docs**: `README.md`
4. **Check implementation**: `IMPLEMENTATION_SUMMARY.md`
5. **Design details**: `../../docs/LOCAL_LLM_INTEGRATION.md`

---

## 💡 Tips

- **Use GPU if available** - 8x faster than CPU
- **Start with Qwen 2.5 3B** - Best balance of size/quality
- **Use 4-bit quantization** if you have limited VRAM
- **Clean cache first** to free up space
- **First download is one-time** - subsequent runs are instant

---

## 🆘 Need Help?

1. Run setup test: `python test_setup.py`
2. Check cache: `python check_cache_sizes.py`
3. Read README: `cat README.md`
4. Check docs: `../../docs/LOCAL_LLM_INTEGRATION.md`

---

**Ready to start? Run**: `python demos/google_search.py` 🚀
