# 🤖 Predicate SDK Playground

**Reproducible demos showing how structure-first browser agents outperform vision-only agents.**

This repository contains **8 real-world browser agent demos** that run using:

* **Semantic geometry snapshots (DOM-based, not vision)**
* **Jest-style AgentRuntime assertions**
* **6 of these 8 demos use local-first inference (Qwen 2.5 3B)**
* **`amazon_shopping` and `google_search` use cloud LLM models for comparison**
* **Optional vision fallback only after exhaustion**

> **TL;DR**
>
> * ✅ 100% task success across all demos
> * 💸 ~50% lower token usage per step
> * 🧠 Works with small local models (3B–7B)
> * ❌ Vision-only agents fail systematically on the same tasks

---

## 🎯 What This Repo Is

This is a **playground + benchmark** for developers evaluating:

* browser agents
* local LLM execution
* deterministic web automation
* flaky UI handling
* assertion-driven verification

Each demo includes:

* runnable code
* logs
* screenshots
* optional video artifacts
* token accounting

---

## 🧪 Canonical Demos (Start Here)

### 🥇 Demo 1: News List Skimming (Hacker News)

**Task**
Open the top "Show HN" post deterministically.

**Why it matters**
This tests *ordinal reasoning* ("first", "top") — a known weakness of vision agents.

**Config**

* Model: Qwen 2.5 3B (local)
* Vision: Disabled
* Assertions: `ordinal=first`, `url_contains`
* Tokens: ~1.6k per step

**Result**
✅ PASS — zero retries, deterministic

![Demo Screenshot](news_list_skimming/screenshots/20260115_215832/scene2_Search_Google_for_'Hacker_News.png)

📂 [`news_list_skimming/`](news_list_skimming/) | [📹 Video](news_list_skimming/video/news_skimming_20260115_215832.mp4)

---

### 🥈 Demo 2: Login + Profile Check (Local Llama Land)

**Task**
Log in, wait for async hydration, verify profile state.

**Why it matters**
Shows **state-aware assertions** (`enabled`, `visible`, `value_equals`) on a modern SPA.

**Config**

* Model: Qwen 2.5 3B (local)
* Vision: Disabled
* Assertions: `eventually()`, `is_enabled`, `text_contains`
* Handles delayed hydration + dynamic state

**Result**
✅ PASS — no sleeps, no magic waits

![Demo Screenshot](login_profile_check/screenshots/20260115_223650/scene4_Click_login_button.png)

📂 [`login_profile_check/`](login_profile_check/) | [📹 Video](login_profile_check/video/login_profile_20260115_223650.mp4)

---

### 🥉 Demo 3: Amazon Shopping Flow (Stress Test)

**Task**
Search product → open result → add to cart.

**Why it matters**
High-noise, JS-heavy, real production site.

**Config**

* Model: Qwen 2.5 3B (local)
* Vision: Disabled (fallback optional)
* Assertions: navigation, button state, success banner
* Tokens: ~5.5k total

**Result**
✅ PASS — vision-only agents failed 3/3 runs

![Demo Screenshot](amazon_shopping_with_assertions/screenshots/20260116_182430/scene4_Pick_first_product_from_search.png)

📂 [`amazon_shopping_with_assertions/`](amazon_shopping_with_assertions/) | [📹 Video](amazon_shopping_with_assertions/video/amazon_shopping_20260116_182430.mp4)

---

## 📊 Key Results (Across All Demos)

| Metric             | Vision-Only | Predicate SDK     |
| ------------------ | ----------- | ----------------- |
| Task success       | ❌ 0–30%     | ✅ 100%            |
| Avg tokens / step  | ~3,000+     | ~1,500            |
| Vision usage       | Required    | Optional fallback |
| Determinism        | No          | Yes               |
| Local model viable | No          | Yes (3B–7B)       |

---

## 🧠 Why This Works

**Vision agents** reason from pixels.
**Predicate agents** reason from *structure*.

Snapshots provide:

* semantic roles
* ordinality
* grouping
* state (enabled, checked, expanded)
* confidence diagnostics

Assertions verify outcomes — not guesses.

## Why Compact Prompts + Local LLMs Work Well

The demo suite consistently succeeds with a small local model (Qwen2.5 3B) using compact, structured prompts:

- **Token efficiency**: ~14.9K tokens across 5 demos vs 100K+ for vision-heavy approaches
- **Reliability**: 5/5 PASS with 0 retries across multi-step flows
- **Speed**: Local text models are faster than vision LLMs for structured UI tasks

See `docs/DEMO_REPORTS.md` for full metrics and results.

---

## 🚀 Quick Start

```bash
git clone https://github.com/PredicateLabs/sentience-sdk-playground
cd sentience-sdk-playground
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install predicatelabs
playwright install chromium
```

### SDK-Python Rename Note (2026-02-10)

- The Python package name changed from `sentienceapi` to `predicatelabs` on **2026-02-10**.
- Use `pip install predicatelabs` for all new setups.
- Canonical imports are now from `predicate` (for example `from predicate import PredicateBrowser, AsyncPredicateBrowser, PredicateDebugger`).
- Canonical API key env var and parameter names are `PREDICATE_API_KEY` and `predicate_api_key`.

If you see runtime/import errors in older examples, there may still be a few stale references. Common examples:

- old: `from sentience ...`
- old: `from predicate.browser import AsyncPredicateBrowser`
- old: `sentience_api_key=...` or `SENTIENCE_API_KEY`

Use these instead:

- new: `from predicate import AsyncPredicateBrowser, PredicateBrowser, PredicateDebugger`
- new: `predicate_api_key=...`
- new: `PREDICATE_API_KEY`

Run a demo:

```bash
cd news_list_skimming
python main.py
```

---

## 📁 Repo Structure

```text
news_list_skimming/              # Ordinality + list reasoning
amazon_shopping_with_assertions/ # Real-world stress test
login_profile_check/             # SPA + form + login flows
dashboard_kpi_extraction/        # KPI extraction + DOM churn
form_validation_submission/      # Multi-step form validation
local-llama-land/               # Demo Next.js site (SPA)
docs/                           # Reports, plans, comparisons
```

---

## 🔗 Learn More

* Predicate SDK (Python): [https://github.com/PredicateLabs/predicatelabs](https://github.com/PredicateLabs/predicatelabs)
* Predicate SDK (TS): [https://github.com/PredicateLabs/sentience-ts](https://github.com/PredicateLabs/sentience-ts)
* Demo Site: [https://sentience-sdk-playground.vercel.app](https://sentience-sdk-playground.vercel.app)
* Docs: [https://predicatelabs.dev/docs](https://predicatelabs.dev/docs)
* Issues: [https://github.com/PredicateLabs/sentience-sdk-playground/issues](https://github.com/PredicateLabs/sentience-sdk-playground/issues)

---

## 🎓 Takeaway

> **Structure replaces vision.
> Assertions replace retries.
> Small models become viable.**

This repo shows that clearly — with real logs, real sites, real results.

---

## 📚 Additional Demos

### Dashboard KPI Extraction

**Task**: Extract KPIs from dynamic dashboard with DOM churn resilience.

![Demo Screenshot](dashboard_kpi_extraction/screenshots/20260115_230444/scene7_Extract_KPI_values.png)

📂 [`dashboard_kpi_extraction/`](dashboard_kpi_extraction/) | [📹 Video](dashboard_kpi_extraction/video/dashboard_kpi_20260115_230444.mp4)

### Form Validation + Submission

**Task**: Complete multi-step form with validation at each step.

📂 [`form_validation_submission/`](form_validation_submission/) | [📹 Video](form_validation_submission/video/form_validation_20260116_164604.mp4) *(screenshots generated locally after running)*

See [`docs/DEMO_REPORTS.md`](docs/DEMO_REPORTS.md) for detailed execution reports and metrics.
