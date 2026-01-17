# Demo Reports

Performance and execution reports for 5 web automation demos using Sentience SDK with local LLM (Qwen2.5 3B) and assertion-based verification.

## Why This Matters

- **Token efficiency**: Structured snapshots enable small local LLMs (3B params) to handle complex automation tasks that typically require vision models or large cloud LLMs, reducing costs by ~90% (14,888 tokens total vs. 100K+ with vision)
- **Deterministic verification**: Assertion-based verification provides machine-verifiable outcomes with retry logic for dynamic content, eliminating reliance on expensive vision model calls for state checks
- **Production readiness**: All 5 demos passed with 0 retries, demonstrating reliability across multi-page navigation, form validation, anti-bot evasion, and DOM churn scenarios

## Overview

**AgentRuntime** provides machine-verifiable agent loops with declarative assertions. Works with local LLMs (Qwen2.5 3B) and cloud LLMs (GPT-4, Claude). **Qwen-3VL** available as vision fallback when LLM exhausts max attempts.

**Assertions**: Predicates (`url_contains`, `exists`, `is_enabled`) evaluate browser state. `runtime.assert_()` evaluates once; `runtime.check().eventually()` retries with fresh snapshots; `runtime.assert_done()` marks task completion. See [Sentience API Documentation](https://www.sentienceapi.com/docs).

**Tracer**: Emits events to Sentience Studio for trace replay, time-travel debugging, and UI diffing visualization.

---

## Demo Results

### 1. [News List Skimming](../news_list_skimming)

**Task**: Find the top story on Hacker News Show page.  
**Model**: Qwen2.5 3B | **Tokens**: 3,294 | **Duration**: 52.2s | **Result**: PASS (5 steps, 0 retries)  
**Key Assertions**: `url_contains("news.ycombinator.com/show")`, `exists("role=link[text*='Show HN']")`  
**Outcome**: LLM identified first "Show HN" post (ordinal position 0) and navigated successfully. Fallback logic corrected initial wrong link selection.

### 2. [Shopping Cart Checkout Flow](../amazon_shopping_with_assertions)

**Task**: Navigate Amazon.com, search, select first product, add to cart, proceed to checkout.  
**Model**: Qwen2.5 3B | **Tokens**: 5,555 | **Duration**: 207.6s | **Result**: PASS (9 steps, 0 retries)  
**Key Assertions**: `url_contains("/dp/{sku}")`, `exists("text~'Add to Cart'")`, `url_contains("signin")` (checkout completion)  
**Outcome**: Completed full e-commerce flow including drawer handling, cart navigation, and checkout initiation. Step 5 took 96.2s due to multiple LLM interactions with Amazon's complex UI.

### 3. [Login + Profile Check](../login_profile_check)

**Task**: Log in to LocalLlamaLand.com, navigate to profile, extract username and email.  
**Model**: Qwen2.5 3B | **Tokens**: 1,283 | **Duration**: 93.8s | **Result**: PASS (6 steps, 0 retries)  
**Key Assertions**: `is_enabled("role=button[text='Sign in']")` (after fields filled), `exists("role=button[text='Edit profile']")` (profile card)  
**Outcome**: Verified button state transitions (disabled → enabled) and extracted profile data after delayed hydration.

### 4. [Interactive SPA Dashboard](../dashboard_kpi_extraction)

**Task**: Extract KPI values from LocalLlamaLand.com dashboard.  
**Model**: Qwen2.5 3B | **Tokens**: 1,326 | **Duration**: 138.1s | **Result**: PASS (9 steps, 0 retries)  
**Key Assertions**: `exists("text~'Llama Coins'")`, `exists("text~'Active Herds'")`, `exists("text~'Messages'")`  
**Outcome**: Extracted 3 KPIs (Llama Coins: 128, Active Herds: 7, Messages: 3) and verified resilience during DOM churn (live updates every 400ms).

### 5. [Form Validation + Submission](../form_validation_submission)

**Task**: Complete multi-step onboarding form with validation at each step.  
**Model**: Qwen2.5 3B | **Tokens**: 3,430 | **Duration**: 185.0s | **Result**: PASS (10 steps, 0 retries)  
**Key Assertions**: `is_enabled("role=button[text='Next']")` (after email, name, plan+terms), `exists("text~'Success'")`  
**Outcome**: Verified button enabled state at each validation step and confirmed success message after submission.

---

## Summary

| Demo | Steps | Retries | Tokens | Duration (s) | Result |
|------|-------|---------|--------|--------------|--------|
| News List Skimming | 5 | 0 | 3,294 | 52.2 | PASS |
| Shopping Cart Checkout Flow | 9 | 0 | 5,555 | 207.6 | PASS |
| Login + Profile Check | 6 | 0 | 1,283 | 93.8 | PASS |
| Interactive SPA Dashboard | 9 | 0 | 1,326 | 138.1 | PASS |
| Form Validation + Submission | 10 | 0 | 3,430 | 185.0 | PASS |
| **Total** | **39** | **0** | **14,888** | **676.7** | **5/5 PASS** |

**Key Assertion Patterns**: Ordinal selection (`first` product), button state (`is_enabled` after validation), content existence (`profile card exists`), URL verification (`url_contains`).

---

## Appendix

### A. Assertion Patterns

**Ordinal Selection**: Goals must include ordinal words when position matters:
- ✅ `"Click the FIRST product in search results"`
- ❌ `"Click a product"` (ambiguous)

**Button State**: Assert enabled/disabled state for form validation:
```python
runtime.assert_(is_enabled("role=button[text='Next']"), label="next_enabled", required=True)
```

**Retry Logic**: Use `eventually()` for dynamic content:
```python
await runtime.check(url_contains("/dp/")).eventually(timeout_s=10.0, poll_s=0.5)
```

### B. Failure Case: Amazon Timing Issue

**Problem**: Step 4 failed despite successful click. URL didn't update immediately due to Amazon's JavaScript-based navigation.

**Root Cause**: Client-side routing updates URL asynchronously (1-3s delay). Initial validation checked URL before JS updated it.

**Fix**: Three-layer approach:
1. Wait for `networkidle` state
2. Explicit 2s timeout for URL update JS
3. Retry-based verification: `runtime.check(url_contains("/dp/")).eventually(timeout_s=10.0)`

**Outcome**: Step 4 now consistently passes. Demonstrates that failures are often timing/validation issues, not LLM comprehension problems.

### C. Vision Model Fallback

**Qwen-3VL** available as fallback when LLM exhausts max attempts. Amazon timing issue didn't trigger fallback because:
- LLM correctly identified and clicked product link
- Click succeeded (`success=True`)
- Failure was in validation logic, not LLM understanding

Fallback remains available for cases where LLM genuinely cannot understand page structure (obfuscated DOM, canvas-based UIs).

### D. Reproduction Steps

**Prerequisites**:
1. Install: `pip install -r requirements.txt && pip install sentienceapi`
2. Get API key: [www.sentienceapi.com](https://www.sentienceapi.com) (free tier available)
3. Set `SENTIENCE_API_KEY` in `.env` or environment

**Enable Visual Overlay**:
```python
from sentience.models import SnapshotOptions
snapshot_options = SnapshotOptions(show_overlay=True, goal="Your task goal here")
```

**Run Demo**: `cd <demo_directory> && python main.py`

**View Traces**: [Sentience Studio](https://www.sentienceapi.com/studio) for replay and debugging (login required).

**Help**: [GitHub Issues](https://github.com/SentienceAPI/sentience-sdk-playground/issues) | [Documentation](https://www.sentienceapi.com/docs)
