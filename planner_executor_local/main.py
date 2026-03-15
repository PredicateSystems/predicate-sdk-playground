#!/usr/bin/env python3
"""
Planner + Executor scaffold for Amazon shopping (local models).

Planner: Qwen 2.5 7B produces a JSON plan.
Executor: Qwen 2.5 3B executes each step with AgentRuntime assertions.

M4 Optimizations:
- Auto device mapping for optimal layer distribution across unified memory
- BFloat16 dtype (optimized for Apple Neural Engine)
- SDPA attention implementation (faster than eager on MPS)
- Low CPU memory usage mode for better memory management

Environment overrides (optional):
- DEVICE_MAP: Set to "mps" or "cpu" to override auto-detection
- TORCH_DTYPE: Set to "bf16", "fp16" to override dtype
"""
from __future__ import annotations

import asyncio
import base64
import builtins
import importlib
import json
import os
import random
import re
import time
import uuid
import hashlib
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "amazon_shopping", "shared")
)
from video_generator_simple import create_demo_video
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "amazon_shopping_with_assertions"))
from main import StepTokenUsage

from predicate.actions import click_async, press_async
from predicate.agent_runtime import AgentRuntime
from predicate.async_api import AsyncPredicateBrowser
from predicate.backends.playwright_backend import PlaywrightBackend
from predicate.backends.sentience_context import SentienceContext
from predicate.cursor_policy import CursorPolicy
from predicate.failure_artifacts import FailureArtifactsOptions
from predicate.llm_provider import LocalVisionLLMProvider, MLXVLMProvider
from predicate.models import Snapshot, SnapshotOptions
from predicate.snapshot_diff import SnapshotDiff
from predicate.trace_event_builder import TraceEventBuilder
from predicate.tracer_factory import create_tracer
from predicate.verification import (
    all_of,
    any_of,
    custom,
    element_count,
    exists,
    not_exists,
    url_contains,
    url_matches,
)
from predicate import CaptchaOptions, HumanHandoffSolver


SEARCH_QUERY = os.getenv("AMAZON_QUERY", "thinkpad")
DEFAULT_PLAN_URL = "https://www.amazon.com"


@dataclass
class LlmResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# ---------------------------------------------------------------------------
# Config: PlannerExecutorConfig (matches design doc + webbench reference)
# ---------------------------------------------------------------------------
@dataclass
class PlannerExecutorConfig:
    """
    Configuration for Planner + Executor agent.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md and webbench/webbench/agents/planner_executor_agent.py.

    Key features:
    - Incremental limit escalation (initial_limit -> max_limit with limit_step increments)
    - Vision fallback configuration
    - Retry settings for verification
    """

    # Snapshot limit escalation settings (from design doc RetryConfig)
    snapshot_limit_base: int = 60
    snapshot_limit_max: int = 200
    snapshot_limit_step: int = 30

    # Retry configuration
    verify_timeout_s: float = 10.0
    verify_poll_s: float = 0.5
    verify_max_attempts: int = 5
    executor_repair_attempts: int = 2

    # Vision fallback
    vision_fallback_enabled: bool = True
    max_vision_calls: int = 3

    # Planner settings
    planner_max_tokens: int = 2048
    planner_repair_attempts: int = 3

    # Executor settings
    executor_max_tokens: int = 96

    # Stabilization (post-action wait for DOM to settle)
    stabilize_enabled: bool = True
    stabilize_poll_s: float = 0.35
    stabilize_max_attempts: int = 6


# ---------------------------------------------------------------------------
# SnapshotContext: Shared page state between Planner and Executor
# ---------------------------------------------------------------------------
@dataclass
class SnapshotContext:
    """
    Shared page state between Planner and Executor to avoid redundant captures.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md Section 3.
    """

    snapshot: Snapshot
    compact_representation: str
    screenshot_base64: str | None
    captured_at: datetime
    limit_used: int
    snapshot_success: bool = True
    requires_vision: bool = False

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        """Check if snapshot is too old to reuse."""
        return (datetime.now() - self.captured_at).total_seconds() > max_age_seconds

    def should_use_vision(self) -> bool:
        """Check if executor should skip snapshot and use vision directly."""
        return not self.snapshot_success or self.requires_vision


def detect_snapshot_failure(snap: Snapshot) -> tuple[bool, str | None]:
    """
    Detect if snapshot is unusable and should trigger vision fallback.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md Section 4.

    Returns:
        (should_use_vision, reason)
    """
    # Check explicit status field (tri-state: success, error, require_vision)
    status = getattr(snap, "status", "success")
    if status == "require_vision":
        return True, "require_vision"

    if status == "error":
        error = getattr(snap, "error", None)
        return True, f"snapshot_error:{error}"

    # Check diagnostics if available
    diag = getattr(snap, "diagnostics", None)
    if diag:
        # Low confidence indicates unreliable snapshot
        confidence = getattr(diag, "confidence", 1.0)
        if confidence is not None and float(confidence) < 0.3:
            return True, "low_confidence"

        # Canvas-heavy pages need vision
        has_canvas = getattr(diag, "has_canvas", False)
        elements = getattr(snap, "elements", []) or []
        if has_canvas and len(elements) < 5:
            return True, "canvas_page"

    # Very few elements usually indicates a problem
    elements = getattr(snap, "elements", []) or []
    if len(elements) < 3:
        return True, "too_few_elements"

    return False, None


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def get_device_map() -> str:
    override = os.getenv("DEVICE_MAP")
    if override:
        return override
    # On Apple Silicon, use "mps" to avoid accelerate auto device_map
    # issues (e.g., inferred max_memory missing "cpu").
    if torch.backends.mps.is_available():
        return "mps"
    return "auto"


def get_torch_dtype() -> torch.dtype:
    override = os.getenv("TORCH_DTYPE")
    if override:
        if override.lower() == "bf16":
            return torch.bfloat16
        if override.lower() == "fp16":
            return torch.float16
    # Use bfloat16 on MPS (Apple Silicon M1/M2/M3/M4) for better performance
    # bfloat16 is optimized for Apple Neural Engine and has better numerical stability
    if torch.backends.mps.is_available():
        return torch.bfloat16
    return torch.float16


class LocalHFModel:
    def __init__(self, model_name: str, device_map: str, torch_dtype: torch.dtype):
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)

        # Build model loading kwargs with MPS-specific optimizations
        load_kwargs = {
            "device_map": device_map,
            "dtype": torch_dtype,
            "low_cpu_mem_usage": True,  # Better memory management for large models
        }

        # MPS-specific optimizations for Apple Silicon (M1/M2/M3/M4)
        if torch.backends.mps.is_available():
            # MPS doesn't support flash attention - use eager or sdpa
            # eager is more stable on MPS but sdpa is faster if available
            load_kwargs["attn_implementation"] = "sdpa"  # Scaled Dot Product Attention
            # Note: If you encounter errors, fallback to "eager"
            # load_kwargs["attn_implementation"] = "eager"

        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                **load_kwargs
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "Invalid buffer size" in msg and torch.backends.mps.is_available():
                raise RuntimeError(
                    "Model allocation failed on MPS (Apple Silicon). "
                    "This usually means the model is too large for the available memory. "
                    "Try a smaller HF model (e.g., Qwen/Qwen2.5-3B-Instruct) or use MLX "
                    "with a 4-bit model (PLANNER_PROVIDER=mlx, EXECUTOR_PROVIDER=mlx)."
                ) from exc
            raise

    def generate(
        self,
        system: str,
        user: str,
        max_new_tokens: int = 256,
        temperature: float = 0.0,
    ) -> LlmResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        encoding = self.tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        )
        device = getattr(self.model, "device", "cpu")
        if hasattr(encoding, "to"):
            encoding = encoding.to(device)
        input_ids = None
        attention_mask = None
        try:
            input_ids = encoding["input_ids"]
            if "attention_mask" in encoding:
                attention_mask = encoding["attention_mask"]
        except Exception:
            input_ids = encoding
        input_ids = input_ids.to(device)
        if attention_mask is not None:
            attention_mask = attention_mask.to(device)
        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids)
        do_sample = temperature > 0
        output_ids = self.model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            temperature=temperature if do_sample else None,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        generated = output_ids[0][input_ids.shape[-1] :]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        prompt_tokens = int(input_ids.shape[-1])
        completion_tokens = int(generated.shape[-1])
        return LlmResult(
            content=text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


class LocalMLXModel:
    def __init__(self, model_name: str):
        self.model_name = model_name
        try:
            self._mlx_lm = importlib.import_module("mlx_lm")
        except Exception as exc:
            raise RuntimeError(
                "mlx-lm is required for MLX text models. Install with: pip install mlx-lm"
            ) from exc
        load_fn = getattr(self._mlx_lm, "load", None)
        if not load_fn:
            raise RuntimeError("mlx_lm.load not available in your mlx-lm install.")
        self.model, self.tokenizer = load_fn(model_name)

    def _build_prompt(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            # Disable thinking mode for Qwen 3.5 models to get direct JSON output
            kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
            if "qwen3" in self.model_name.lower():
                kwargs["enable_thinking"] = False
            return apply_chat_template(messages, **kwargs)
        return f"{system}\n\n{user}"

    def generate(
        self,
        system: str,
        user: str,
        max_new_tokens: int = 256,
        temperature: float = 0.0,
    ) -> LlmResult:
        prompt = self._build_prompt(system, user)
        generate_fn = getattr(self._mlx_lm, "generate", None)
        if not generate_fn:
            raise RuntimeError("mlx_lm.generate not available in your mlx-lm install.")
        kwargs: dict[str, Any] = {"max_tokens": max_new_tokens}
        if temperature and temperature > 0:
            try:
                sample_utils = importlib.import_module("mlx_lm.sample_utils")
                make_sampler = getattr(sample_utils, "make_sampler", None)
                if callable(make_sampler):
                    kwargs["sampler"] = make_sampler(temp=temperature)
            except Exception:
                pass
        text = generate_fn(
            self.model,
            self.tokenizer,
            prompt,
            **kwargs,
        )
        # mlx-lm doesn't expose token usage directly, so we calculate it
        # using the tokenizer
        try:
            prompt_tokens = len(self.tokenizer.encode(prompt))
            completion_tokens = len(self.tokenizer.encode(text.strip()))
        except Exception:
            prompt_tokens = 0
            completion_tokens = 0
        return LlmResult(
            content=text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


def extract_json(text: str) -> dict[str, Any]:
    # Strip DeepSeek R1 thinking tokens (</think> marks end of reasoning)
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()
    # Also handle plain "think" without XML tags (some models output this way)
    # Look for common patterns that indicate end of reasoning
    for marker in ["</think>", "\n\n```json", "\n```json", "\n\n{"]:
        if marker in text:
            idx = text.find(marker)
            if marker.startswith("\n"):
                text = text[idx:].strip()
            break

    # Prefer fenced JSON blocks if present.
    fence_match = re.search(r"```json\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if fence_match:
        return json.loads(fence_match.group(1))
    # Fallback: first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in planner output")
    return json.loads(text[start : end + 1])


def parse_click_id(text: str) -> int | None:
    m = re.search(r"CLICK\s*\(\s*(\d+)\s*\)", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def emit_snapshot_trace(runtime: AgentRuntime, snap: Snapshot) -> None:
    if not snap:
        return
    prev = getattr(runtime, "_trace_prev_snapshot", None)
    try:
        elements_with_diff = SnapshotDiff.compute_diff_status(snap, prev)
        payload = snap.model_dump()
        payload["elements"] = elements_with_diff
        snap_with_diff = Snapshot(**payload)
    except Exception:
        snap_with_diff = snap
    setattr(runtime, "_trace_prev_snapshot", snap)
    setattr(runtime, "_trace_last_snapshot", snap_with_diff)

    # Include step_index for Studio compatibility
    step_index = getattr(runtime, "step_index", None)
    snapshot_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)
    if step_index is not None:
        snapshot_data["step_index"] = step_index

    if snap.screenshot:
        screenshot_base64 = (
            snap.screenshot.split(",", 1)[1]
            if snap.screenshot.startswith("data:image")
            else snap.screenshot
        )
        snapshot_data["screenshot_base64"] = screenshot_base64
        if snap.screenshot_format:
            snapshot_data["screenshot_format"] = snap.screenshot_format
    runtime.tracer.emit(
        "snapshot",
        snapshot_data,
        step_id=getattr(runtime, "step_id", None),
    )


def _compute_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def find_no_thanks_button_id(snap) -> int | None:
    if not snap or not getattr(snap, "elements", None):
        return None
    candidates = []
    for el in snap.elements:
        try:
            if getattr(el, "role", "") != "button":
                continue
            text = (getattr(el, "text", "") or "").strip()
            if "no thanks" not in text.lower():
                continue
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None)
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y if doc_y is not None else 1e9, -importance, el.id))
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def drawer_visible_in_snapshot(snap) -> bool:
    if not snap or not getattr(snap, "elements", None):
        return False
    for el in snap.elements:
        try:
            text = (getattr(el, "text", "") or "").strip()
            nearby = (getattr(el, "nearby_text", "") or "").strip()
            combined = f"{text} {nearby}".strip().lower()
            if (
                "no thanks" in combined
                or "add protection" in combined
                or "add to your order" in combined
            ):
                return True
        except Exception:
            continue
    return False


def find_checkout_button_id(snap) -> int | None:
    if not snap or not getattr(snap, "elements", None):
        return None
    candidates = []
    for el in snap.elements:
        try:
            el_id = getattr(el, "id", None)
            if not isinstance(el_id, int) or el_id <= 0:
                continue
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"button", "link"}:
                continue
            text = (getattr(el, "text", "") or "").strip()
            nearby = (getattr(el, "nearby_text", "") or "").strip()
            combined = f"{text} {nearby}".strip()
            lowered = combined.lower()
            if "checkout" not in lowered and "proceed to checkout" not in lowered:
                continue
            if (
                "add to cart" in lowered
                or "buy now" in lowered
                or "add protection" in lowered
                or "no thanks" in lowered
            ):
                continue
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None)
            importance = getattr(el, "importance", 0) or 0
            is_checkout_button = 0 if "checkout" in lowered else 1
            candidates.append(
                (
                    not in_viewport,
                    is_checkout_button,
                    doc_y if doc_y is not None else 1e9,
                    -importance,
                    el_id,
                )
            )
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][4]  # el_id is at index 4


def find_search_box_id(snap) -> int | None:
    if not snap or not getattr(snap, "elements", None):
        return None
    candidates = []
    for el in snap.elements:
        try:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"searchbox", "textbox", "combobox"}:
                continue
            text = (getattr(el, "text", "") or "").strip()
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None)
            importance = getattr(el, "importance", 0) or 0
            prefers_search = 0 if "search" in text.lower() else 1
            candidates.append(
                (
                    not in_viewport,
                    prefers_search,
                    doc_y if doc_y is not None else 1e9,
                    -importance,
                    el.id,
                )
            )
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][4]


def find_first_product_link_id(snap, keyword: str) -> int | None:
    """
    Find the first valid product link in search results.

    Prioritization:
    1. Links with /dp/ or /gp/product/ in href (REQUIRED - these are product pages)
    2. Links containing the search keyword in text (preferred but not required)
    3. Links with lower doc_y (higher on page)
    4. Links with higher importance

    Explicitly excludes:
    - Filter/refinement links (refinements= in href)
    - Sponsored labels and menu items
    """
    if not snap or not getattr(snap, "elements", None):
        return None
    key = (keyword or "").strip().lower()
    candidates = []
    for el in snap.elements:
        try:
            role = (getattr(el, "role", "") or "").lower()
            if role != "link":
                continue
            href = (getattr(el, "href", "") or "").lower()
            # REQUIRED: Must be a product page link
            if "/dp/" not in href and "/gp/product/" not in href:
                continue
            # EXCLUDE: Filter/refinement links
            if "refinements=" in href or "rh=" in href:
                continue
            text = (getattr(el, "text", "") or "").strip()
            # Skip empty text or very short text (likely icons)
            if not text or len(text) < 3:
                continue
            # Skip obvious non-product items
            text_lower = text.lower()
            if any(skip in text_lower for skip in [
                "sponsored", "free shipping", "prime", "filter", "sort by",
                "amazon haul", "see all", "show more"
            ]):
                continue
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None)
            importance = getattr(el, "importance", 0) or 0
            # Prioritize: keyword match (0=has keyword, 1=no keyword), viewport, doc_y, importance
            has_keyword = 0 if key and key in text_lower else 1
            candidates.append(
                (has_keyword, not in_viewport, doc_y if doc_y is not None else 1e9, -importance, el.id)
            )
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][4]


def is_valid_product_link(snap, element_id: int) -> bool:
    """
    Check if the executor's click choice is a valid product link.

    Returns True if the element:
    - Is a link with href containing /dp/ or /gp/product/, OR
    - Is a link with product-like text (brand + product name) and NOT a filter/rating link

    Returns False if the element:
    - Contains refinements= or rh= (filter links)
    - Is a star rating link
    - Has text indicating a filter/sponsored item

    This is used to validate executor selections before clicking.
    """
    if not snap or not getattr(snap, "elements", None) or element_id is None:
        return False
    for el in snap.elements:
        try:
            if getattr(el, "id", None) != element_id:
                continue
            role = (getattr(el, "role", "") or "").lower()
            if role != "link":
                return False
            href = (getattr(el, "href", "") or "").lower()
            text = (getattr(el, "text", "") or "").strip().lower()

            # Explicit filter links are invalid
            if "refinements=" in href or "rh=" in href:
                return False

            # Rating/star links are invalid
            if "out of 5 stars" in text or "rating" in text:
                return False

            # Filter-like text patterns are invalid
            filter_patterns = [
                "free shipping", "apply", "filter", "prime", "sponsored ad -",
                "see more", "show more", "a icon", "checkbox",
                "traditional laptops", "customer ratings", "credit card",
                "no annual fee", "cash back", "reward points"
            ]
            if any(p in text for p in filter_patterns):
                return False

            # If href has product path, it's valid
            if "/dp/" in href or "/gp/product/" in href:
                return True

            # If text looks like a product title, accept it even without /dp/ in href
            # Product titles typically have brand + specs (e.g., "Lenovo ThinkPad E16 Gen 2 Business...")
            # This handles JavaScript-navigated links where href might not contain the full path
            if len(text) > 10:
                # Check for product-like patterns (brand names, model numbers, specs)
                product_indicators = [
                    "thinkpad", "lenovo", "laptop", "computer", "notebook",
                    "gen ", "business", "16gb", "32gb", "ssd", "ram", "ddr"
                ]
                if any(ind in text for ind in product_indicators):
                    return True

            return False
        except Exception:
            continue
    return False


def find_add_to_cart_button_id(snap) -> int | None:
    if not snap or not getattr(snap, "elements", None):
        return None
    candidates = []
    for el in snap.elements:
        try:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if "add to cart" not in lowered:
                continue
            if "buy now" in lowered:
                continue
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None)
            importance = getattr(el, "importance", 0) or 0
            candidates.append(
                (not in_viewport, doc_y if doc_y is not None else 1e9, -importance, el.id)
            )
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def build_planner_prompt(
    task: str,
    strict: bool = False,
    schema_errors: str | None = None,
    *,
    start_url: str | None = None,
    site_type: str | None = None,
    auth_state: str | None = None,
    planner_mode: str | None = None,
) -> tuple[str, str]:
    system = (
        "You are the PLANNER. Output a JSON plan for an Executor to run.\n"
        "The Executor can only click/type using element IDs from snapshots.\n"
        "Include explicit verification predicates per step.\n"
        "Use stop_if_true for sign-in redirect after checkout.\n"
        "If 'Add to Cart' is not found on a product page, include optional substeps to scroll down and retry.\n"
        "Avoid brittle selectors like class=... for search-result clicks; prefer URL-based verifies.\n"
        "If a soft-block page appears on Amazon with a 'Click to Continue' button, "
        "include an optional substep to detect and click it.\n"
        "Do NOT hardcode product URLs like /dp/product-url; use a CLICK step on the first product link.\n"
        "Return ONLY a JSON object. No explanations, no <think> tags, no code fences."
    )
    strict_note = (
        "\nReturn ONLY a JSON object. Do not include any other text.\n"
        if strict
        else ""
    )
    schema_note = (
        f"\nSchema/smoothness issues from last attempt:\n{schema_errors}\n"
        if schema_errors
        else ""
    )
    mode = (planner_mode or os.getenv("PLANNER_MODE", "diet")).lower()
    affordances = []
    site = (site_type or "commerce").lower()
    if site == "commerce":
        affordances = [
            "There is usually a search box in the header.",
            "Search results appear as a repeated list of product links.",
            "Product pages typically have an 'Add to Cart' button.",
            "A cart/checkout button appears after adding to cart.",
        ]
    elif site == "search":
        affordances = [
            "There is a search box near the top.",
            "Results appear as a repeated list of links.",
        ]

    payload = {
        "task": task,
        "done_when": ["url contains /dp/ after click", "checkout is reachable"],
        "start_url": start_url or DEFAULT_PLAN_URL,
        "site_type": site,
        "auth_state": auth_state or "unknown",
        "constraints": {
            "max_steps": 8,
            "no_vision": True,
            "abort_on_captcha": True,
            "allowed_actions": ["navigate", "click", "type", "press", "scroll", "wait", "assert"],
        },
        "ui_affordances": affordances if mode in {"diet_hints", "diet+hints"} else [],
        "output_schema": {
            "steps": [
                {
                    "id": 1,
                    "goal": "string",
                    "action": "NAVIGATE|CLICK|TYPE_AND_SUBMIT|SCROLL",
                    "intent": "string",
                    "target": "natural language target (no selectors)",
                    "input": "optional",
                    "verify": ["1-2 predicate specs"],
                }
            ]
        },
    }
    payload_text = json.dumps(payload, indent=2)
    user = f"""
Task payload (diet mode):
{payload_text}
{strict_note}

Planner contract:
- Use ONLY the fields in the schema example below.
- Max required steps: 8 (optional_substeps do not count).
- One action per step. Do not repeat similar CLICK intents back-to-back.
- For search flows, the core template is mandatory:
  NAVIGATE → CLICK(search_box) → TYPE_AND_SUBMIT(query) → CLICK(first_product_link) → CLICK(add_to_cart) → NAVIGATE(cart) → CLICK(proceed_to_checkout)
- Every required step must include >=1 verify predicate.
- Avoid fragile verify-only checks (e.g., exists("role=textbox")) unless paired with a
  more specific predicate.
- For first_product_link, use verify url_contains("/dp/") instead of class selectors.
- Allowed actions: NAVIGATE, CLICK, TYPE_AND_SUBMIT, SCROLL.

Predicates allowed: url_contains, url_matches, exists, not_exists, element_count, any_of, all_of.
Note: url_contains expects a single string; use any_of for multiple options.

Step archetypes (choose from these only):
1) NAVIGATE(target=url, verify=[url_contains|url_matches])
2) CLICK(intent=..., verify=[exists/not_exists/url_contains/any_of/all_of])
3) TYPE_AND_SUBMIT(input=..., verify=[url_contains|url_matches])
4) SCROLL(target=down|up, verify=[optional])

Output JSON with fields:
- task: string
- notes: list of strings
- steps: list of steps (id, goal, action, target/intent/input, verify, required, stop_if_true?, optional_substeps?)

Format example (match keys exactly):
{{
  "task": "Amazon shopping cart checkout flow",
  "notes": ["Executor uses stealth typing", "Stop on sign-in redirect"],
  "steps": [
    {{
      "id": 1,
      "goal": "Navigate to Amazon homepage",
      "action": "NAVIGATE",
      "target": "https://www.amazon.com",
      "verify": [{{ "predicate": "url_contains", "args": ["amazon."] }}],
      "required": true
    }},
    {{
      "id": 2,
      "goal": "Focus the search box",
      "action": "CLICK",
      "intent": "search_box",
      "verify": [{{ "predicate": "any_of", "args": [
        {{ "predicate": "exists", "args": ["role=searchbox"] }},
        {{ "predicate": "exists", "args": ["role=textbox"] }},
        {{ "predicate": "exists", "args": ["role=combobox"] }}
      ]}}],
      "required": true
    }},
    {{
      "id": 3,
      "goal": "Type search query and submit",
      "action": "TYPE_AND_SUBMIT",
      "input": "thinkpad",
      "verify": [{{ "predicate": "url_contains", "args": ["k=thinkpad"] }}],
      "required": true
    }},
    {{
      "id": 4,
      "goal": "Click the first product in search results, go to product details page",
      "action": "CLICK",
      "intent": "first_product_link",
      "verify": [{{ "predicate": "url_contains", "args": ["/dp/"] }}],
      "required": true
    }},
    {{
      "id": 5,
      "goal": "Click the 'Add to Cart' button",
      "action": "CLICK",
      "intent": "add_to_cart",
      "verify": [{{ "predicate": "any_of", "args": [
        {{ "predicate": "exists", "args": ["text~'Added to Cart'"] }},
        {{ "predicate": "url_contains", "args": ["cart"] }}
      ]}}],
      "required": true,
      "optional_substeps": [
        {{
          "id": 1,
          "goal": "Scroll down if the Add to Cart button is not visible",
          "action": "SCROLL",
          "target": "down",
          "required": false
        }},
        {{
          "id": 2,
          "goal": "Retry clicking Add to Cart after scrolling",
          "action": "CLICK",
          "intent": "add_to_cart_retry",
          "verify": [{{ "predicate": "any_of", "args": [
            {{ "predicate": "exists", "args": ["text~'Added to Cart'"] }},
            {{ "predicate": "url_contains", "args": ["cart"] }}
          ]}}],
          "required": false
        }},
        {{
          "id": 3,
          "goal": "If 'Add to Your Order' drawer appears, click 'No thanks'",
          "action": "CLICK",
          "intent": "drawer_no_thanks",
          "verify": [{{ "predicate": "not_exists", "args": ["text~'Add to Your Order'"] }}],
          "required": false
        }}
      ]
    }}
    ,
    {{
      "id": 6,
      "goal": "Navigate to cart page",
      "action": "NAVIGATE",
      "target": "https://www.amazon.com/gp/cart/view.html",
      "verify": [{{ "predicate": "any_of", "args": [
        {{ "predicate": "url_contains", "args": ["cart"] }},
        {{ "predicate": "exists", "args": ["text~'Subtotal'"] }}
      ]}}],
      "required": true
    }},
    {{
      "id": 7,
      "goal": "Proceed to checkout",
      "action": "CLICK",
      "intent": "proceed_to_checkout",
      "verify": [{{ "predicate": "any_of", "args": [
        {{ "predicate": "url_contains", "args": ["signin"] }},
        {{ "predicate": "url_contains", "args": ["/ap/"] }},
        {{ "predicate": "url_contains", "args": ["checkout"] }}
      ]}}],
      "required": true,
      "stop_if_true": true
    }}
  ]
}}

Unsmooth example (INVALID):
{{"steps":[
  {{"id":1,"action":"CLICK","intent":"search_box","verify":[{{"predicate":"any_of","args":[{{"predicate":"exists","args":["role=searchbox"]}},{{"predicate":"exists","args":["role=textbox"]}}]}}],"required":true}},
  {{"id":2,"action":"CLICK","intent":"search_box","verify":[{{"predicate":"any_of","args":[{{"predicate":"exists","args":["role=searchbox"]}},{{"predicate":"exists","args":["role=textbox"]}}]}}],"required":true}}
]}}
Reason: redundant CLICK intents back-to-back.

Smooth example (VALID):
{{"steps":[
  {{"id":1,"action":"CLICK","intent":"search_box","verify":[{{"predicate":"any_of","args":[{{"predicate":"exists","args":["role=searchbox"]}},{{"predicate":"exists","args":["role=textbox"]}}]}}],"required":true}},
  {{"id":2,"action":"TYPE_AND_SUBMIT","input":"thinkpad","verify":[{{"predicate":"url_contains","args":["k=thinkpad"]}}],"required":true}}
]}}

{schema_note}
"""
    return system, user


def extract_plan_with_retry(
    planner: LocalHFModel, task: str, max_attempts: int = 2
) -> tuple[dict[str, Any], str]:
    last_output = ""
    last_errors = ""
    planner_name = str(getattr(planner, "model_name", ""))
    planner_requires_strict = (
        os.getenv("PLANNER_STRICT", "1").lower() in {"1", "true", "yes"}
        or "deepseek-r1" in planner_name.lower()
    )
    for attempt in range(1, max_attempts + 1):
        max_tokens = 1536 if attempt == 1 else 2048
        sys_prompt, user_prompt = build_planner_prompt(
            task,
            strict=(planner_requires_strict or attempt > 1),
            schema_errors=last_errors or None,
            start_url=DEFAULT_PLAN_URL,
            site_type="commerce",
            auth_state="unknown",
            planner_mode=os.getenv("PLANNER_MODE", "diet"),
        )
        resp = planner.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=max_tokens
        )
        last_output = resp.content
        try:
            plan = extract_json(resp.content)
            plan = normalize_plan(plan)
            errors = validate_plan(plan)
            smoothness = validate_plan_smoothness(plan, task)
            if errors or smoothness:
                combined = []
                if errors:
                    combined.extend(errors)
                if smoothness:
                    combined.extend(smoothness)
                last_errors = "\n".join(f"- {e}" for e in combined)
                continue
            return plan, last_output
        except Exception:
            continue
    raise RuntimeError(
        f"Planner failed to return JSON after {max_attempts} attempts.\nRaw output:\n{last_output}"
    )


def build_replan_prompt(
    task: str,
    failed_step_id: int | None,
    failure_code: str,
    short_note: str,
    failed_step: dict[str, Any] | None = None,
    strict: bool = False,
    schema_errors: str | None = None,
) -> tuple[str, str]:
    system = (
        "You are the PLANNER. Output a JSON patch to edit an existing plan.\n"
        "Edit ONLY the failed step (by id) and optionally the next step.\n"
        "Do not change earlier successful steps.\n"
        "Actions must be one of: NAVIGATE, CLICK, TYPE_AND_SUBMIT.\n"
        "Do NOT hardcode product URLs like /dp/product-url; use CLICK on a product link.\n"
        "IMPORTANT: Preserve working verify predicates. If url_contains('/dp/') was correct, keep it.\n"
        "Only change the action or intent, not the verify predicates, unless the predicate itself was wrong.\n"
        "Return ONLY a JSON object. No explanations, no <think> tags, no code fences."
    )
    strict_note = (
        "\nReturn ONLY a JSON object. Do not include any other text.\n"
        if strict
        else ""
    )
    schema_note = (
        f"\nSchema errors from last attempt:\n{schema_errors}\n"
        if schema_errors
        else ""
    )
    # Include the original failed step so the planner can see the original verify predicates
    original_step_json = ""
    if failed_step:
        import json
        original_step_json = f"\nOriginal failed step:\n{json.dumps(failed_step, indent=2)}\n"

    # Build example that preserves original verify if available
    example_verify = '[{ "predicate": "url_contains", "args": ["/dp/"] }]'
    if failed_step and "verify" in failed_step:
        import json
        example_verify = json.dumps(failed_step["verify"])

    user = f"""
Task: {task}
{strict_note}

Failure summary:
- failed_step_id: {failed_step_id}
- failure_code: {failure_code}
- note: {short_note}
{original_step_json}{schema_note}

IMPORTANT: The verify predicates in the original step were likely CORRECT.
The failure was probably in the action/intent selection, NOT the verification.
PRESERVE the original verify predicates unless you are certain they were wrong.

Return JSON in PATCH mode:
{{
  "mode": "patch",
  "replace_steps": [
    {{
      "id": {failed_step_id or 1},
      "step": {{
        "id": {failed_step_id or 1},
        "goal": "Rewrite the failed step with same verify predicates",
        "action": "CLICK",
        "intent": "first_product_link",
        "verify": {example_verify},
        "required": true
      }}
    }}
  ]
}}

If you must return a full plan, omit "mode" and include "steps".
"""
    return system, user


def extract_replan_with_retry(
    planner: LocalHFModel,
    task: str,
    current_plan: dict[str, Any],
    failed_step_id: int | None,
    failure_code: str,
    short_note: str,
    failed_step: dict[str, Any] | None = None,
    max_attempts: int = 2,
) -> tuple[dict[str, Any], str, str]:
    last_output = ""
    last_errors = ""
    planner_name = str(getattr(planner, "model_name", ""))
    planner_requires_strict = (
        os.getenv("PLANNER_STRICT", "1").lower() in {"1", "true", "yes"}
        or "deepseek-r1" in planner_name.lower()
    )
    for attempt in range(1, max_attempts + 1):
        max_tokens = 1024 if attempt == 1 else 1536
        sys_prompt, user_prompt = build_replan_prompt(
            task,
            failed_step_id=failed_step_id,
            failure_code=failure_code,
            short_note=short_note,
            failed_step=failed_step,
            strict=(planner_requires_strict or attempt > 1),
            schema_errors=last_errors or None,
        )
        resp = planner.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=max_tokens
        )
        last_output = resp.content
        try:
            plan_or_patch = extract_json(resp.content)
            mode = str(plan_or_patch.get("mode") or "").lower()
            if mode == "patch" or "replace_steps" in plan_or_patch:
                patched = apply_replan_patch(current_plan, plan_or_patch)
                patched = normalize_plan(patched)
                errors = validate_plan(patched)
                smoothness = validate_plan_smoothness(patched, task)
                if errors or smoothness:
                    combined = []
                    if errors:
                        combined.extend(errors)
                    if smoothness:
                        combined.extend(smoothness)
                    last_errors = "\n".join(f"- {e}" for e in combined)
                    continue
                return patched, last_output, "patch"
            plan = normalize_plan(plan_or_patch)
            errors = validate_plan(plan)
            smoothness = validate_plan_smoothness(plan, task)
            if errors or smoothness:
                combined = []
                if errors:
                    combined.extend(errors)
                if smoothness:
                    combined.extend(smoothness)
                last_errors = "\n".join(f"- {e}" for e in combined)
                continue
            return plan, last_output, "full"
        except Exception:
            continue
    schema_block = ""
    if last_errors:
        schema_block = "Schema errors:\n" + last_errors + "\n"
    raise RuntimeError(
        "Planner failed to return valid replan JSON after "
        f"{max_attempts} attempts.\n"
        f"{schema_block}Raw output:\n{last_output}"
    )


def build_executor_prompt(
    goal: str, intent: str | None, compact: str
) -> tuple[str, str]:
    intent_line = f"Intent: {intent}\n" if intent else ""
    system = "You are a careful web agent. Output only CLICK(<id>)."
    intent_lower = (intent or "").lower()
    extra_rules = ""
    if intent_lower in {"first_product_link", "first_search_result"}:
        extra_rules = (
            "CRITICAL RULES FOR SEARCH RESULTS:\n"
            "1) ONLY click product links whose href contains '/dp/' or '/gp/product/'.\n"
            "2) IGNORE all filter/refinement links with 'refinements=' in href (e.g., 'Free Shipping', 'Prime').\n"
            "3) IGNORE menu items, rating links, top nav links, and sponsored labels.\n"
            "4) Prefer links with ord=0 (first product) in the dominant group (DG=1).\n"
            "5) High importance score does NOT mean it's a product - filter links often have high scores.\n"
            "6) Product links typically show product names/titles, not filter options.\n\n"
        )
    elif intent_lower in {"search_box", "search_input"}:
        extra_rules = (
            "CRITICAL RULES FOR SEARCH BOX:\n"
            "1) Click the search input (role=searchbox/textbox/combobox).\n"
            "2) Do NOT click language links or settings (e.g., 'Choose a language for shopping').\n"
            "3) Prefer inputs with placeholder text containing 'Search'.\n\n"
        )
    elif intent_lower in {"add_to_cart", "add_to_cart_retry"}:
        extra_rules = (
            "CRITICAL RULES FOR ADD TO CART:\n"
            "1) Click the 'Add to cart' button on the product page.\n"
            "2) If a drawer/popup shows 'No thanks', click 'No thanks' instead.\n"
            "3) Do NOT click 'Buy now' or product links.\n\n"
        )
    elif intent_lower in {"drawer_no_thanks", "no_thanks"}:
        extra_rules = (
            "CRITICAL RULES FOR ADD-ON DRAWER:\n"
            "1) Click the button labeled 'No thanks' (case-insensitive) in the add-on drawer.\n"
            "2) Ignore other buttons like 'Add to Order', 'Add protection', or primary CTA.\n"
            "3) Do NOT click 'Add to cart' or 'Buy now' while the drawer is visible.\n"
            "4) If multiple 'No thanks' options exist, choose the one inside the drawer.\n\n"
        )
    elif intent_lower in {"proceed_to_checkout", "checkout"}:
        extra_rules = (
            "CRITICAL RULES FOR CHECKOUT:\n"
            "1) Click the 'Proceed to checkout' button.\n"
            "2) Do NOT click product links, sponsored items, or add-on offers.\n\n"
        )
    user = (
        "You are controlling a browser via element IDs.\n\n"
        "You must respond with exactly ONE action in this format:\n"
        "- CLICK(<id>)\n\n"
        "SNAPSHOT FORMAT EXPLANATION:\n"
        "The snapshot shows elements in this format: "
        "ID|role|text|importance|is_primary|bg|bg_fallback|clickable|nearby_text|docYq|ord|DG|href|\n"
        "- ID: Element ID (use this for CLICK)\n"
        "- role: Element type (link, button, textbox, etc.)\n"
        "- text: Visible text content or placeholder\n"
        "- importance: Importance score (higher = more important)\n"
        "- is_primary: 1 if primary action, 0 otherwise\n"
        "- bg: background_color_name (semantic name)\n"
        "- bg_fallback: fallback_background_color_name (best-effort)\n"
        "- clickable: 1 if clickable, 0 otherwise\n"
        "- nearby_text: nearby static text (best-effort)\n"
        "- docYq: Vertical position bucket\n"
        "- ord: Rank in dominant group (0 = first)\n"
        "- DG: 1 if in dominant group, 0 otherwise\n"
        "- href: URL if link element\n\n"
        f"Goal: {goal}\n"
        f"{intent_line}"
        f"{extra_rules}"
        "Elements (ID|role|text|imp|is_primary|bg|bg_fallback|clickable|nearby_text|docYq|ord|DG|href):\n"
        f"{compact}\n"
    )
    return system, user


def normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize planner outputs to the expected schema:
    - map `url` -> `target`
    - normalize action casing and aliases
    """
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return plan
    for step in steps:
        if not isinstance(step, dict):
            continue
        if "url" in step and "target" not in step:
            step["target"] = step.pop("url")
        action = step.get("action")
        if isinstance(action, str):
            action_upper = action.strip().upper()
            if action_upper == "TYPE":
                action_upper = "TYPE_AND_SUBMIT"
            step["action"] = action_upper
        intent = step.get("intent")
        if isinstance(intent, str):
            intent_lower = intent.strip().lower()
            if intent_lower in {"product_link", "first_product", "product_list_item"}:
                step["intent"] = "first_product_link"
            if intent_lower in {"dismiss_drawer", "no_thanks_button", "no_thanks"}:
                step["intent"] = "drawer_no_thanks"
            if intent_lower in {"add_to_cart_button", "add_to_cart_btn"}:
                step["intent"] = "add_to_cart"
            if intent_lower in {"checkout_button", "checkout_cta"}:
                step["intent"] = "proceed_to_checkout"
        verify = step.get("verify")
        if isinstance(verify, list):
            for v in verify:
                if not isinstance(v, dict):
                    continue
                # Normalize url_contains with multiple args to any_of(url_contains)
                if v.get("predicate") == "url_contains" and isinstance(
                    v.get("args"), list
                ):
                    args = v["args"]
                    if len(args) > 1 and all(isinstance(a, str) for a in args):
                        v["predicate"] = "any_of"
                        v["args"] = [
                            {"predicate": "url_contains", "args": [a]} for a in args
                        ]
                if v.get("predicate") == "url_matches" and isinstance(
                    v.get("args"), list
                ):
                    args = v["args"]
                    if args and isinstance(args[0], str) and "/dp/" in args[0]:
                        v["predicate"] = "url_contains"
                        v["args"] = ["/dp/"]
        if str(step.get("intent") or "").lower() == "proceed_to_checkout":
            if (
                isinstance(verify, list)
                and len(verify) == 1
                and isinstance(verify[0], dict)
                and verify[0].get("predicate") == "exists"
                and verify[0].get("args") == ["role=button"]
            ):
                step["verify"] = [
                    {
                        "predicate": "any_of",
                        "args": [
                            {"predicate": "url_contains", "args": ["signin"]},
                            {"predicate": "url_contains", "args": ["/ap/"]},
                            {"predicate": "url_contains", "args": ["checkout"]},
                        ],
                    }
                ]
        if str(step.get("intent") or "").lower() == "first_product_link":
            if isinstance(verify, list) and verify:
                has_class_selector = False
                for v in verify:
                    if not isinstance(v, dict):
                        continue
                    if v.get("predicate") in {"exists", "not_exists"}:
                        args = v.get("args") or []
                        if (
                            isinstance(args, list)
                            and len(args) == 1
                            and isinstance(args[0], str)
                            and "class=" in args[0]
                        ):
                            has_class_selector = True
                            break
                if has_class_selector:
                    step["verify"] = [{"predicate": "url_contains", "args": ["/dp/"]}]
        target = step.get("target")
        if isinstance(target, str) and "product-url" in target:
            # Replace placeholder product URL with a proper click intent.
            step.pop("target", None)
            step["action"] = "CLICK"
            step["intent"] = step.get("intent") or "first_product_link"
            step["goal"] = (
                step.get("goal") or "Click the FIRST product link in search results"
            )
            step["verify"] = [{"predicate": "url_contains", "args": ["/dp/"]}]
    return plan


def is_search_results_url(url: str, query: str) -> bool:
    current = (url or "").lower()
    keyword_in_url = f"k={query.lower()}" in current
    search_url_pattern = ("/s" in current) or ("s?k=" in current) or ("/s/" in current)
    not_product_page = "/dp/" not in current and "/gp/product/" not in current
    not_homepage = not (
        current.endswith("amazon.com/")
        or current.endswith("amazon.com")
        or current.rstrip("/").endswith("amazon.com")
    )
    return (keyword_in_url or search_url_pattern) and not_product_page and not_homepage


def format_verify_specs(verify: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for spec in verify:
        predicate = spec.get("predicate", "")
        args = spec.get("args", [])
        lines.append(f"- {predicate}({args})")
    return "\n".join(lines) if lines else "- (none)"


def is_yes(text: str) -> bool:
    return text.strip().upper().startswith("YES")


async def get_page_screenshot_base64(browser: AsyncPredicateBrowser) -> str:
    png_bytes = await browser.page.screenshot(full_page=False)
    return base64.b64encode(png_bytes).decode("ascii")


async def vision_fallback_check(
    *,
    vision_llm: Any,
    browser: AsyncPredicateBrowser,
    goal: str,
    verify: list[dict[str, Any]],
    reason: str,
) -> tuple[bool, str]:
    if vision_llm is None:
        return False, "vision_disabled"
    image_b64 = await get_page_screenshot_base64(browser)
    system = "You are a visual verifier. Answer strictly YES or NO."
    user = (
        "Question: Based on the screenshot, is the step goal already satisfied?\n"
        f"Goal: {goal}\n"
        "Verification hints:\n"
        f"{format_verify_specs(verify)}\n"
        f"Reason: {reason}\n"
        "Answer only YES or NO."
    )
    resp = vision_llm.generate_with_image(
        system, user, image_b64, max_new_tokens=16, temperature=0.0
    )
    return is_yes(resp.content or ""), (resp.content or "").strip()


async def vision_select_click_id(
    *,
    vision_llm: Any,
    browser: AsyncPredicateBrowser,
    goal: str,
    compact: str,
    reason: str,
) -> tuple[int | None, str]:
    if vision_llm is None:
        return None, "vision_disabled"
    image_b64 = await get_page_screenshot_base64(browser)
    system = "You are a visual selector. Output only CLICK(<id>)."
    user = (
        "Select the best element ID from the snapshot list based on the screenshot.\n"
        f"Goal: {goal}\n"
        f"Reason: {reason}\n\n"
        "Snapshot format: "
        "ID|role|text|importance|is_primary|bg|bg_fallback|clickable|nearby_text|docYq|ord|DG|href|\n"
        "Snapshot list (ID|role|text|imp|is_primary|bg|bg_fallback|clickable|nearby_text|docYq|ord|DG|href):\n"
        f"{compact}\n\n"
        "Return ONLY: CLICK(<id>)"
    )
    resp = vision_llm.generate_with_image(
        system, user, image_b64, max_new_tokens=24, temperature=0.0
    )
    click_id = parse_click_id(resp.content or "")
    return click_id, (resp.content or "").strip()


def build_predicate(spec: dict[str, Any]):
    name = spec.get("predicate")
    args = spec.get("args", [])
    if name == "url_contains":
        return url_contains(args[0])
    if name == "url_matches":
        pattern = args[0]
        if (
            isinstance(pattern, str)
            and "/dp/" in pattern
            and not pattern.startswith("http")
        ):
            return url_contains("/dp/")
        return url_matches(pattern)
    if name == "exists":
        return exists(args[0])
    if name == "not_exists":
        return not_exists(args[0])
    if name == "element_count":
        selector = args[0]
        min_count = args[1] if len(args) > 1 else 0
        max_count = args[2] if len(args) > 2 else None
        return element_count(selector, min_count=min_count, max_count=max_count)
    if name == "any_of":
        return any_of(*(build_predicate(p) for p in args))
    if name == "all_of":
        return all_of(*(build_predicate(p) for p in args))
    raise ValueError(f"Unsupported predicate: {name}")


async def apply_verifications(
    runtime: AgentRuntime, verify: list[dict[str, Any]], required: bool,
    config: PlannerExecutorConfig | None = None
) -> bool:
    """
    Apply predicate-based verifications with incremental limit escalation.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md Section 4: Incremental Limit Escalation.

    If verification fails, we retry with progressively larger snapshot limits:
    - initial_limit (e.g., 60) -> +step (e.g., 90) -> +step (e.g., 120) -> ... -> max_limit (e.g., 200)

    This helps find elements that may be outside the initial snapshot window.
    """
    if not verify:
        return True

    # Use defaults if config not provided
    cfg = config or PlannerExecutorConfig()

    ok_all = True
    for idx, v in enumerate(verify, start=1):
        pred = build_predicate(v)
        label = v.get("label") or f"verify_{idx}"

        if required:
            # Incremental limit escalation for required verifications
            current_limit = cfg.snapshot_limit_base
            attempt = 0

            while current_limit <= cfg.snapshot_limit_max:
                attempt += 1
                # Update snapshot limit via options if possible
                opts = getattr(runtime, "snapshot_options", None)
                if opts is not None:
                    opts.limit = current_limit

                print(
                    f"    [verify_debug] Calling runtime.check with required=True, label={label}",
                    flush=True,
                )
                ok = await runtime.check(pred, label=label, required=True).eventually(
                    timeout_s=cfg.verify_timeout_s,
                    poll_s=cfg.verify_poll_s,
                    max_snapshot_attempts=cfg.verify_max_attempts
                )
                print(
                    f"    [verify_debug] runtime.check.eventually() returned ok={ok}",
                    flush=True,
                )

                if ok:
                    break

                # Escalate limit for next attempt
                if current_limit < cfg.snapshot_limit_max:
                    print(
                        f"  [verify] Escalating snapshot limit: {current_limit} -> {min(current_limit + cfg.snapshot_limit_step, cfg.snapshot_limit_max)} "
                        f"(predicate={v.get('predicate')})",
                        flush=True,
                    )
                    current_limit = min(current_limit + cfg.snapshot_limit_step, cfg.snapshot_limit_max)
                else:
                    break

            ok_all = ok_all and bool(ok)
        else:
            ok = runtime.assert_(pred, label=label, required=False)
            ok_all = ok_all and bool(ok)

    return ok_all


async def snapshot_with_escalation(
    runtime: AgentRuntime,
    ctx_formatter: Any,
    goal: str,
    config: PlannerExecutorConfig | None = None,
    capture_screenshot: bool = False,
) -> SnapshotContext:
    """
    Capture snapshot with incremental limit escalation and vision fallback detection.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md Section 3 (SnapshotContext) and
    webbench/webbench/agents/planner_executor_agent.py (_snapshot_with_ramp).

    Returns:
        SnapshotContext with snapshot, compact representation, and vision fallback flags.
    """
    cfg = config or PlannerExecutorConfig()
    current_limit = cfg.snapshot_limit_base
    last_snap: Snapshot | None = None
    last_compact: str = ""
    screenshot_b64: str | None = None
    requires_vision = False
    vision_reason: str | None = None

    while current_limit <= cfg.snapshot_limit_max:
        try:
            snap = await runtime.snapshot(
                limit=current_limit,
                screenshot=capture_screenshot,
                goal=goal
            )
            if snap is None:
                print(f"  [snapshot] Got None at limit={current_limit}", flush=True)
                current_limit = min(current_limit + cfg.snapshot_limit_step, cfg.snapshot_limit_max + 1)
                continue

            last_snap = snap

            # Check if snapshot indicates vision fallback needed
            needs_vision, reason = detect_snapshot_failure(snap)
            if needs_vision:
                requires_vision = True
                vision_reason = reason
                print(f"  [snapshot] Vision fallback needed: {reason}", flush=True)
                # Still return the snapshot, but flag it for vision
                break

            # Generate compact representation
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            last_compact = compact

            # Check if we have enough elements
            elements = getattr(snap, "elements", []) or []
            if len(elements) >= 10:  # Reasonable threshold
                break

            # Escalate if we got too few elements
            if current_limit < cfg.snapshot_limit_max:
                print(
                    f"  [snapshot] Low element count ({len(elements)}), escalating: {current_limit} -> {current_limit + cfg.snapshot_limit_step}",
                    flush=True,
                )
                current_limit = min(current_limit + cfg.snapshot_limit_step, cfg.snapshot_limit_max)
            else:
                break

        except Exception as exc:
            print(f"  [snapshot] Error at limit={current_limit}: {exc}", flush=True)
            current_limit = min(current_limit + cfg.snapshot_limit_step, cfg.snapshot_limit_max + 1)

    # Fallback: return empty context if no snapshot obtained
    if last_snap is None:
        # Create a minimal Snapshot to indicate failure
        last_snap = Snapshot(
            status="error",
            elements=[],
            url="",
            title="",
            error="snapshot_capture_failed"
        )
        requires_vision = True
        vision_reason = "snapshot_capture_failed"
        print(f"  [snapshot] {vision_reason}", flush=True)

    return SnapshotContext(
        snapshot=last_snap,
        compact_representation=last_compact,
        screenshot_base64=screenshot_b64,
        captured_at=datetime.now(),
        limit_used=current_limit,
        snapshot_success=not requires_vision,
        requires_vision=requires_vision,
    )


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _validate_predicate_spec(spec: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return [f"{path}: predicate spec must be object"]
    if "predicate" not in spec or not isinstance(spec["predicate"], str):
        errors.append(f"{path}: missing or invalid 'predicate'")
        return errors

    predicate = spec["predicate"]
    args = spec.get("args", [])
    if predicate in {"url_contains", "url_matches", "exists", "not_exists"}:
        if not (isinstance(args, list) and len(args) == 1 and isinstance(args[0], str)):
            errors.append(f"{path}: '{predicate}' expects args: [string]")
    elif predicate == "element_count":
        if not (isinstance(args, list) and len(args) >= 1 and isinstance(args[0], str)):
            errors.append(
                f"{path}: 'element_count' expects args: [selector, min?, max?]"
            )
    elif predicate in {"any_of", "all_of"}:
        if not isinstance(args, list) or not args:
            errors.append(f"{path}: '{predicate}' expects args: [predicate_spec, ...]")
        else:
            for i, sub in enumerate(args):
                errors.extend(_validate_predicate_spec(sub, f"{path}.args[{i}]"))
    else:
        errors.append(f"{path}: unsupported predicate '{predicate}'")
    return errors


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_actions = {"NAVIGATE", "CLICK", "TYPE_AND_SUBMIT", "SCROLL"}
    allowed_step_keys = {
        "id",
        "goal",
        "action",
        "target",
        "intent",
        "input",
        "verify",
        "required",
        "stop_if_true",
        "optional_substeps",
    }

    if not isinstance(plan, dict):
        return ["plan: must be an object"]
    if not isinstance(plan.get("task"), str):
        errors.append("plan.task must be a string")
    if "notes" in plan and not _is_str_list(plan.get("notes")):
        errors.append("plan.notes must be a list of strings")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("plan.steps must be a non-empty list")
        return errors

    last_id: int | None = None
    expected_id = 1
    for i, step in enumerate(steps):
        path = f"plan.steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{path} must be an object")
            continue
        extra_keys = {k for k in step.keys() if k not in allowed_step_keys and not k.startswith("_")}
        if extra_keys:
            errors.append(f"{path} has unsupported keys: {sorted(extra_keys)}")
        if not isinstance(step.get("id"), int):
            errors.append(f"{path}.id must be int")
        else:
            step_id = step["id"]
            if step_id != expected_id:
                errors.append(
                    f"{path}.id must be contiguous starting at 1 (expected={expected_id})"
                )
            last_id = step_id
            expected_id += 1
        if not isinstance(step.get("goal"), str):
            errors.append(f"{path}.goal must be string")
        action = step.get("action")
        if not isinstance(action, str):
            errors.append(f"{path}.action must be string")
        elif action.upper() not in allowed_actions:
            errors.append(f"{path}.action must be one of {sorted(allowed_actions)}")
        if "required" in step and not isinstance(step.get("required"), bool):
            errors.append(f"{path}.required must be bool")
        if "stop_if_true" in step and not isinstance(step.get("stop_if_true"), bool):
            errors.append(f"{path}.stop_if_true must be bool")
        if "verify" in step:
            verify = step.get("verify")
            if not isinstance(verify, list):
                errors.append(f"{path}.verify must be a list")
            else:
                for j, v in enumerate(verify):
                    errors.extend(_validate_predicate_spec(v, f"{path}.verify[{j}]"))
        if step.get("required", False) and not step.get("verify"):
            errors.append(f"{path}.verify is required when step.required is true")
        if "optional_substeps" in step:
            subs = step.get("optional_substeps")
            if not isinstance(subs, list):
                errors.append(f"{path}.optional_substeps must be a list")
            else:
                last_sub_id: int | None = None
                sub_expected_id: int | None = None
                for k, sub in enumerate(subs):
                    sub_path = f"{path}.optional_substeps[{k}]"
                    if not isinstance(sub, dict):
                        errors.append(f"{sub_path} must be an object")
                        continue
                    extra = {
                        k
                        for k in sub.keys()
                        if k not in allowed_step_keys and not k.startswith("_")
                    }
                    if extra:
                        errors.append(
                            f"{sub_path} has unsupported keys: {sorted(extra)}"
                        )
                    if "id" in sub:
                        if not isinstance(sub.get("id"), int):
                            errors.append(f"{sub_path}.id must be int when provided")
                        else:
                            sub_id = sub["id"]
                            if sub_expected_id is None:
                                if sub_id != 1:
                                    errors.append(
                                        f"{sub_path}.id must start at 1 (got={sub_id})"
                                    )
                                sub_expected_id = 1
                            if sub_id != sub_expected_id:
                                errors.append(
                                    f"{sub_path}.id must be contiguous (expected={sub_expected_id})"
                                )
                            if last_sub_id is not None and sub_id <= last_sub_id:
                                errors.append(
                                    f"{sub_path}.id must be strictly increasing (prev={last_sub_id})"
                                )
                            last_sub_id = sub_id
                            sub_expected_id += 1
                    elif last_sub_id is not None:
                        errors.append(
                            f"{sub_path}.id required once any optional_substeps have ids"
                        )
                    if not isinstance(sub.get("goal"), str):
                        errors.append(f"{sub_path}.goal must be string")
                    sub_action = sub.get("action")
                    if not isinstance(sub_action, str):
                        errors.append(f"{sub_path}.action must be string")
                    elif sub_action.upper() not in allowed_actions:
                        errors.append(
                            f"{sub_path}.action must be one of {sorted(allowed_actions)}"
                        )
                    if "verify" in sub:
                        verify = sub.get("verify")
                        if not isinstance(verify, list):
                            errors.append(f"{sub_path}.verify must be a list")
                        else:
                            for j, v in enumerate(verify):
                                errors.extend(
                                    _validate_predicate_spec(
                                        v, f"{sub_path}.verify[{j}]"
                                    )
                                )
    return errors


def apply_replan_patch(
    current_plan: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    steps = current_plan.get("steps")
    if not isinstance(steps, list):
        raise ValueError("current_plan.steps must be a list")
    replace_steps = patch.get("replace_steps")
    if not isinstance(replace_steps, list) or not replace_steps:
        raise ValueError("patch.replace_steps must be a non-empty list")

    by_id = {s.get("id"): i for i, s in enumerate(steps) if isinstance(s, dict)}
    for item in replace_steps:
        if not isinstance(item, dict):
            raise ValueError("patch.replace_steps items must be objects")
        step_id = item.get("id")
        step_obj = item.get("step")
        if not isinstance(step_id, int):
            raise ValueError("patch.replace_steps.id must be int")
        if not isinstance(step_obj, dict):
            raise ValueError("patch.replace_steps.step must be object")
        if step_id not in by_id:
            raise ValueError(f"patch target id not found: {step_id}")
        step_obj["id"] = step_id
        steps[by_id[step_id]] = step_obj
    current_plan["steps"] = steps
    return current_plan


def validate_plan_smoothness(plan: dict[str, Any], task: str) -> list[str]:
    errors: list[str] = []
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return errors

    required_steps = [s for s in steps if isinstance(s, dict) and s.get("required", False)]
    if len(required_steps) > 8:
        errors.append("smoothness: too many required steps (>8)")

    prev_click_intent: str | None = None
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").upper()
        intent = str(step.get("intent") or "").lower()
        if action == "CLICK":
            if prev_click_intent and intent and intent == prev_click_intent:
                errors.append(f"smoothness: redundant CLICK intent back-to-back: {intent}")
            prev_click_intent = intent or prev_click_intent
        else:
            prev_click_intent = None

        if step.get("required", False):
            verify = step.get("verify") or []
            if (
                isinstance(verify, list)
                and len(verify) == 1
                and isinstance(verify[0], dict)
                and verify[0].get("predicate") == "exists"
                and verify[0].get("args") == ["role=textbox"]
            ):
                if str(step.get("intent") or "").lower() != "search_box":
                    errors.append(
                        "smoothness: required step verify is too generic (role=textbox only)"
                    )

    intents = [str(s.get("intent") or "").lower() for s in steps if isinstance(s, dict)]
    actions = [str(s.get("action") or "").upper() for s in steps if isinstance(s, dict)]
    if any(i in intents for i in ["search_box", "first_product_link"]) or any(
        a == "TYPE_AND_SUBMIT" for a in actions
    ):
        idx_navigate = next(
            (i for i, s in enumerate(steps) if str(s.get("action") or "").upper() == "NAVIGATE"),
            None,
        )
        idx_search = next(
            (i for i, s in enumerate(steps) if str(s.get("intent") or "").lower() == "search_box"),
            None,
        )
        idx_type = next(
            (
                i
                for i, s in enumerate(steps)
                if str(s.get("action") or "").upper() == "TYPE_AND_SUBMIT"
            ),
            None,
        )
        idx_first = next(
            (
                i
                for i, s in enumerate(steps)
                if str(s.get("intent") or "").lower() == "first_product_link"
            ),
            None,
        )
        if idx_navigate is None or idx_search is None or idx_type is None or idx_first is None:
            errors.append("smoothness: missing mandatory search flow template steps")
        else:
            if not (idx_navigate < idx_search < idx_type < idx_first):
                errors.append("smoothness: search flow steps out of order")

    return errors


def ensure_minimum_plan(plan: dict[str, Any], query: str) -> dict[str, Any]:
    """
    Guardrail: if planner returns only a focus-click step, append the
    remaining baseline steps from the advanced plan.
    """
    steps = plan.get("steps") or []
    has_type = any(s.get("action", "").upper() == "TYPE_AND_SUBMIT" for s in steps)
    if has_type:
        return plan

    baseline = [
        {
            "id": 2,
            "goal": "Type search query with human-like jitter and submit",
            "action": "TYPE_AND_SUBMIT",
            "input": query,
            "verify": [{"predicate": "url_contains", "args": [f"k={query.lower()}"]}],
            "required": True,
        },
        {
            "id": 3,
            "goal": "Click the FIRST product link in search results",
            "action": "CLICK",
            "intent": "first_product_link",
            "verify": [{"predicate": "url_contains", "args": ["/dp/"]}],
            "required": True,
        },
        {
            "id": 4,
            "goal": "Click the 'Add to cart' button and handle optional drawer popup",
            "action": "CLICK",
            "intent": "add_to_cart",
            "verify": [
                {
                    "predicate": "any_of",
                    "args": [
                        {"predicate": "exists", "args": ["text~'Added to Cart'"]},
                        {"predicate": "url_contains", "args": ["cart"]},
                    ],
                }
            ],
            "required": True,
            "optional_substeps": [
                {
                    "id": 1,
                    "goal": "Scroll down if the 'Add to cart' button is not visible",
                    "action": "SCROLL",
                    "target": "down",
                    "required": False,
                },
                {
                    "id": 2,
                    "goal": "Retry clicking 'Add to cart' after scrolling",
                    "action": "CLICK",
                    "intent": "add_to_cart_retry",
                    "verify": [
                        {
                            "predicate": "any_of",
                            "args": [
                                {"predicate": "exists", "args": ["text~'Added to Cart'"]},
                                {"predicate": "url_contains", "args": ["cart"]},
                            ],
                        }
                    ],
                    "required": False,
                },
                {
                    "id": 3,
                    "goal": "If 'Add to Your Order' drawer appears, click 'No thanks'",
                    "action": "CLICK",
                    "intent": "drawer_no_thanks",
                    "verify": [
                        {
                            "predicate": "not_exists",
                            "args": ["text~'Add to Your Order'"],
                        }
                    ],
                    "required": False,
                },
            ],
        },
        {
            "id": 5,
            "goal": "Navigate to cart page",
            "action": "NAVIGATE",
            "target": "https://www.amazon.com/gp/cart/view.html",
            "verify": [
                {
                    "predicate": "any_of",
                    "args": [
                        {"predicate": "url_contains", "args": ["cart"]},
                        {"predicate": "exists", "args": ["text~'Subtotal'"]},
                    ],
                }
            ],
            "required": True,
        },
        {
            "id": 6,
            "goal": "Click the 'Proceed to checkout' button",
            "action": "CLICK",
            "intent": "proceed_to_checkout",
            "verify": [
                {
                    "predicate": "any_of",
                    "args": [
                        {"predicate": "url_contains", "args": ["signin"]},
                        {"predicate": "url_contains", "args": ["/ap/"]},
                        {"predicate": "url_contains", "args": ["checkout"]},
                    ],
                }
            ],
            "required": True,
            "stop_if_true": True,
        },
    ]

    # Preserve existing step 1, then append baseline with contiguous ids.
    new_steps = []
    if steps:
        new_steps.append(steps[0])
    new_steps.extend(baseline)
    for idx, step in enumerate(new_steps, start=1):
        step["id"] = idx
    plan["steps"] = new_steps
    return plan


async def type_with_stealth(page, text: str):
    for ch in text:
        await page.keyboard.type(ch)
        await page.wait_for_timeout(random.randint(40, 140))
        if random.random() < 0.08:
            await page.wait_for_timeout(random.randint(180, 520))


async def run_executor_step(
    step: dict[str, Any],
    runtime: AgentRuntime,
    browser: AsyncPredicateBrowser,
    executor: LocalHFModel,
    ctx_formatter: SentienceContext,
    cursor_policy: CursorPolicy,
    vision_llm: Any,
    feedback_path: Path,
    run_id: str,
) -> tuple[bool, str]:
    goal = step.get("goal", "Execute step")
    action = step.get("action", "").upper()
    intent = step.get("intent")
    required = bool(step.get("required", False))
    verify = step.get("verify", [])

    runtime.begin_step(goal)
    pre_url = browser.page.url if browser.page else None
    runtime.tracer.emit_step_start(
        step_id=getattr(runtime, "step_id", "step-0"),
        step_index=getattr(runtime, "step_index", 0),
        goal=goal,
        attempt=0,
        pre_url=pre_url,
    )
    setattr(runtime, "_trace_step_pre_url", pre_url)

    if action == "NAVIGATE":
        target = step.get("target", DEFAULT_PLAN_URL)
        await browser.goto(target)
        await browser.page.wait_for_load_state("domcontentloaded", timeout=15_000)
        await runtime.record_action("NAVIGATE")
        snap = await runtime.snapshot()
        if snap is not None:
            emit_snapshot_trace(runtime, snap)
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            print("\n--- Compact prompt (snapshot) ---", flush=True)
            print(compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
        return ok, "navigated"

    if action == "TYPE_AND_SUBMIT":
        # Ensure search box is focused before typing
        pre_snap = await runtime.snapshot(
            limit=50, screenshot=False, goal="Focus search box before typing"
        )
        if pre_snap is not None:
            emit_snapshot_trace(runtime, pre_snap)
            pre_compact = ctx_formatter._format_snapshot_for_llm(pre_snap)
            print("\n--- Compact prompt (pre-type snapshot) ---", flush=True)
            print(pre_compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
            focus_goal = "Click the search input box (role=searchbox or role=textbox) before typing."
            sys_prompt, user_prompt = build_executor_prompt(
                focus_goal, "search_box", pre_compact
            )
            preferred_id = None
            try:
                preferred_id = find_search_box_id(pre_snap)
                if preferred_id is not None:
                    print(
                        f"  [fallback] search_box preselect -> CLICK({preferred_id})",
                        flush=True,
                    )
            except Exception as exc:
                print(f"  [warn] search_box preselect failed: {exc}", flush=True)
            focus_resp = executor.generate(
                sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24
            )
            setattr(
                runtime,
                "_trace_last_llm",
                {
                    "response_text": focus_resp.content,
                    "response_hash": f"sha256:{_compute_hash(focus_resp.content)}",
                    "usage": {
                        "prompt_tokens": focus_resp.prompt_tokens,
                        "completion_tokens": focus_resp.completion_tokens,
                        "total_tokens": focus_resp.total_tokens,
                    },
                },
            )
            runtime.tracer.emit(
                "llm_called",
                {
                    "model": executor.model_name,
                    "goal": focus_goal,
                    "intent": "search_box",
                    "compact_context": pre_compact,
                    "prompt_tokens": focus_resp.prompt_tokens,
                    "completion_tokens": focus_resp.completion_tokens,
                    "total_tokens": focus_resp.total_tokens,
                    "response_text": focus_resp.content,
                },
                step_id=getattr(runtime, "step_id", None),
            )
            focus_id = parse_click_id(focus_resp.content)
            print(
                "  Executor decision:",
                json.dumps(
                    {
                        "action": "click",
                        "id": focus_id,
                        "raw": focus_resp.content,
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
            if preferred_id is not None and preferred_id != focus_id:
                print(
                    f"  [override] search_box -> CLICK({preferred_id})",
                    flush=True,
                )
                focus_id = preferred_id
            if focus_id is not None:
                await click_async(
                    browser, focus_id, use_mouse=True, cursor_policy=cursor_policy
                )
                await browser.page.wait_for_timeout(400)
                await runtime.record_action("CLICK")

        text = step.get("input", SEARCH_QUERY)
        await type_with_stealth(browser.page, text)
        # Fallback: if the input value didn't stick, set it via JS and retype.
        try:
            current_value = await browser.page.evaluate(
                "(() => { const el = document.activeElement; return el && el.value ? el.value : ''; })()"
            )
        except Exception:
            current_value = ""
        if not current_value or text.lower() not in str(current_value).lower():
            try:
                await browser.page.evaluate(
                    "(q) => { const el = document.activeElement; if (el) { el.value = q; el.dispatchEvent(new Event('input', { bubbles: true })); } }",
                    text,
                )
                await browser.page.wait_for_timeout(300)
            except Exception:
                pass
            await type_with_stealth(browser.page, text)
        await press_async(browser, "Enter")
        await browser.page.wait_for_load_state("domcontentloaded", timeout=15_000)
        await runtime.record_action("TYPE_AND_SUBMIT")
        try:
            await browser.page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        await browser.page.wait_for_timeout(1500)
        current_url = browser.page.url
        if not is_search_results_url(current_url, SEARCH_QUERY):
            print(f"  [error] Could not verify search results page", flush=True)
            print(f"  [error] Current URL: {current_url}", flush=True)
            return False, "search_results_not_verified"
        # Ensure search results exist before snapshot for downstream steps
        await runtime.check(
            any_of(
                element_count("role=link[href*='/dp/']", min_count=3),
                element_count("role=link[href*='/gp/product/']", min_count=3),
            ),
            label="search_results_links_present",
            required=False,
        ).eventually(timeout_s=10.0, poll_s=0.5, max_snapshot_attempts=10)
        snap = await runtime.snapshot(
            limit=80, screenshot=False, goal="Search results snapshot"
        )
        if snap is not None:
            emit_snapshot_trace(runtime, snap)
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            print("\n--- Compact prompt (snapshot) ---", flush=True)
            print(compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
        return ok, "typed_and_submitted"

    if action == "SCROLL":
        direction = str(step.get("target") or "down").lower()
        amount = 900
        if isinstance(step.get("input"), (int, float)):
            amount = int(step["input"])
        if direction in {"up", "top"}:
            amount = -abs(amount)
        else:
            amount = abs(amount)
        await browser.page.mouse.wheel(0, amount)
        await browser.page.wait_for_timeout(900)
        await runtime.record_action("SCROLL")
        snap = await runtime.snapshot(limit=60, screenshot=False, goal=goal)
        if snap is not None:
            emit_snapshot_trace(runtime, snap)
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            print("\n--- Compact prompt (snapshot) ---", flush=True)
            print(compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
        return ok, "scrolled"

    if action == "CLICK":
        intent_lower = (intent or "").lower()
        exec_goal = goal
        if intent_lower == "add_to_cart":
            exec_goal = "Click the 'Add to Cart' button."
        snap_limit = (
            60
            if intent_lower in {"drawer_no_thanks", "no_thanks"}
            else (
                60
                if intent_lower
                in {"search_box", "first_product_link", "first_search_result", "proceed_to_checkout", "checkout"}
                else 60
            )
        )
        if intent_lower in {"first_product_link", "first_search_result"}:

            def _has_product_links(ctx) -> bool:
                snap = ctx.snapshot
                if not snap:
                    return False
                for el in snap.elements:
                    href = (el.href or "").lower()
                    if (
                        "/dp/" in href
                        or "/gp/product/" in href
                        or "/gp/slredirect/" in href
                        or "dp%2f" in href
                    ):
                        return True
                return False

            links_ok = await runtime.check(
                custom(_has_product_links, label="product_links_present"),
                label="product_links_present",
                required=False,
            ).eventually(timeout_s=12.0, poll_s=0.5, max_snapshot_attempts=12)
            if not links_ok:
                print(
                    "  [warn] product links not detected yet; proceeding with snapshot",
                    flush=True,
                )
            snap_limit = 200
        snap = await runtime.snapshot(limit=snap_limit, screenshot=False, goal=exec_goal)
        if snap is None:
            return False, "snapshot_missing"
        emit_snapshot_trace(runtime, snap)
        compact = ctx_formatter._format_snapshot_for_llm(snap)
        print("\n--- Compact prompt (snapshot) ---", flush=True)
        print(compact, flush=True)
        print("--- end compact prompt ---\n", flush=True)
        preferred_id = None
        if intent_lower in {"drawer_no_thanks", "no_thanks"}:
            try:
                preferred_id = find_no_thanks_button_id(snap)
                if preferred_id is not None:
                    print(
                        f"  [fallback] drawer_no_thanks preselect -> CLICK({preferred_id})",
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"  [warn] drawer_no_thanks preselect failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"add_to_cart", "add_to_cart_retry"}:
            try:
                drawer_id = find_no_thanks_button_id(snap)
                if drawer_id is not None:
                    preferred_id = drawer_id
                    print(
                        f"  [fallback] add_to_cart drawer detected -> CLICK({preferred_id})",
                        flush=True,
                    )
                else:
                    preferred_id = find_add_to_cart_button_id(snap)
                    if preferred_id is not None:
                        print(
                            f"  [fallback] add_to_cart preselect -> CLICK({preferred_id})",
                            flush=True,
                        )
            except Exception as exc:
                print(
                    f"  [warn] add_to_cart drawer preselect failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"first_product_link", "first_search_result"}:
            try:
                preferred_id = find_first_product_link_id(snap, SEARCH_QUERY)
                if preferred_id is not None:
                    print(
                        f"  [fallback] first_product_link preselect -> CLICK({preferred_id})",
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"  [warn] first_product_link preselect failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"proceed_to_checkout", "checkout"}:
            try:
                preferred_id = find_checkout_button_id(snap)
                if preferred_id is not None and preferred_id > 0:
                    print(
                        f"  [fallback] proceed_to_checkout preselect -> CLICK({preferred_id})",
                        flush=True,
                    )
                elif preferred_id is not None:
                    print(
                        f"  [warn] proceed_to_checkout preselect ignored non-positive id: {preferred_id}",
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"  [warn] proceed_to_checkout preselect failed: {exc}",
                    flush=True,
                )

        sys_prompt, user_prompt = build_executor_prompt(exec_goal, intent, compact)
        resp = executor.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24
        )
        setattr(
            runtime,
            "_trace_last_llm",
            {
                "response_text": resp.content,
                "response_hash": f"sha256:{_compute_hash(resp.content)}",
                "usage": {
                    "prompt_tokens": resp.prompt_tokens,
                    "completion_tokens": resp.completion_tokens,
                    "total_tokens": resp.total_tokens,
                },
            },
        )
        runtime.tracer.emit(
            "llm_called",
            {
                "model": executor.model_name,
                "goal": exec_goal,
                "intent": intent,
                "compact_context": compact,
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "total_tokens": resp.total_tokens,
                "response_text": resp.content,
            },
            step_id=getattr(runtime, "step_id", None),
        )
        click_id = parse_click_id(resp.content)
        print(
            "  Executor decision:",
            json.dumps(
                {
                    "action": "click",
                    "id": click_id,
                    "raw": resp.content,
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        if intent_lower in {"drawer_no_thanks", "no_thanks"}:
            try:
                if preferred_id is not None and preferred_id != click_id:
                    print(
                        f"  [override] drawer_no_thanks -> CLICK({preferred_id})",
                        flush=True,
                    )
                    click_id = preferred_id
            except Exception as exc:
                print(
                    f"  [warn] drawer_no_thanks override failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"add_to_cart", "add_to_cart_retry"}:
            try:
                if preferred_id is not None and preferred_id != click_id:
                    print(
                        f"  [override] add_to_cart -> CLICK({preferred_id})",
                        flush=True,
                    )
                    click_id = preferred_id
            except Exception as exc:
                print(
                    f"  [warn] add_to_cart drawer override failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"first_product_link", "first_search_result"}:
            try:
                # Validate executor's choice: must be a valid product link (not a filter)
                executor_choice_valid = is_valid_product_link(snap, click_id)
                if not executor_choice_valid and click_id is not None:
                    print(
                        f"  [validate] executor picked invalid element {click_id} (not a product link)",
                        flush=True,
                    )
                if preferred_id is not None and (
                    preferred_id != click_id or not executor_choice_valid
                ):
                    print(
                        f"  [override] first_product_link -> CLICK({preferred_id}) "
                        f"(executor_valid={executor_choice_valid})",
                        flush=True,
                    )
                    click_id = preferred_id
                elif not executor_choice_valid and preferred_id is None:
                    # Executor choice invalid and no fallback - try to find any valid product link
                    fallback_id = find_first_product_link_id(snap, "")
                    if fallback_id is not None:
                        print(
                            f"  [override] no preferred_id, using fallback -> CLICK({fallback_id})",
                            flush=True,
                        )
                        click_id = fallback_id
            except Exception as exc:
                print(
                    f"  [warn] first_product_link override failed: {exc}",
                    flush=True,
                )
        elif intent_lower in {"proceed_to_checkout", "checkout"}:
            try:
                if (
                    preferred_id is not None
                    and preferred_id > 0
                    and preferred_id != click_id
                ):
                    print(
                        f"  [override] proceed_to_checkout -> CLICK({preferred_id})",
                        flush=True,
                    )
                    click_id = preferred_id
            except Exception as exc:
                print(
                    f"  [warn] proceed_to_checkout override failed: {exc}",
                    flush=True,
                )
        if click_id is None:
            runtime.assert_(
                exists("role=button"), label="llm_failed_to_pick_click", required=True
            )
            vision_id, vision_text = await vision_select_click_id(
                vision_llm=vision_llm,
                browser=browser,
                goal=goal,
                compact=compact,
                reason="executor_missing_click_id",
            )
            if vision_id is not None:
                append_jsonl(
                    feedback_path,
                    {
                        "event": "vision_select",
                        "run_id": run_id,
                        "step": step,
                        "reason": "executor_missing_click_id",
                        "vision_response": vision_text,
                        "selected_id": vision_id,
                    },
                )
                click_id = vision_id
            else:
                return False, "llm_click_id_missing"
        pre_url = browser.page.url if browser.page else ""
        await click_async(
            browser, click_id, use_mouse=True, cursor_policy=cursor_policy
        )
        await browser.page.wait_for_timeout(1200)
        await runtime.record_action("CLICK")
        snap_after = await runtime.snapshot()
        post_url = browser.page.url if browser.page else ""
        url_changed = bool(pre_url and post_url and pre_url != post_url)
        step["_url_changed"] = url_changed
        compact_after = None
        if snap_after is not None:
            emit_snapshot_trace(runtime, snap_after)
            compact_after = ctx_formatter._format_snapshot_for_llm(snap_after)
            print("\n--- Compact prompt (post-click snapshot) ---", flush=True)
            print(compact_after, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        if intent_lower == "add_to_cart" and drawer_visible_in_snapshot(snap_after):
            print(
                "  [info] add_to_cart drawer detected post-click; handling before verify",
                flush=True,
            )
            drawer_step = {
                "goal": "Dismiss the add-on drawer by clicking 'No thanks'",
                "action": "CLICK",
                "intent": "drawer_no_thanks",
                "verify": [
                    {
                        "predicate": "not_exists",
                        "args": ["text~'Add to Your Order'"],
                    }
                ],
                "required": False,
            }
            await run_executor_step(
                drawer_step,
                runtime,
                browser,
                executor,
                ctx_formatter,
                cursor_policy,
                vision_llm,
                feedback_path,
                run_id,
            )
            step["_drawer_handled"] = True
        print(
            f"  [debug] apply_verifications: verify={verify}, required={required}",
            flush=True,
        )
        ok = await apply_verifications(runtime, verify, required)
        print(
            f"  [debug] apply_verifications returned: ok={ok}",
            flush=True,
        )
        if not ok and required and (intent or "").lower() == "search_box":
            # Amazon sometimes reports the search input as searchbox/combobox, not textbox.
            alt_ok = await runtime.check(
                any_of(
                    exists("role=searchbox"),
                    exists("role=textbox"),
                    exists("role=combobox"),
                ),
                label="search_box_present_alt",
                required=False,
            ).eventually(timeout_s=3.0, poll_s=0.3, max_snapshot_attempts=3)
            if alt_ok:
                return True, "search_box_detected_alt"
        if not ok and required:
            vision_id, vision_text = await vision_select_click_id(
                vision_llm=vision_llm,
                browser=browser,
                goal=goal,
                compact=compact_after or compact,
                reason="verification_failed",
            )
            if vision_id is not None:
                append_jsonl(
                    feedback_path,
                    {
                        "event": "vision_select",
                        "run_id": run_id,
                        "step": step,
                        "reason": "verification_failed",
                        "vision_response": vision_text,
                        "selected_id": vision_id,
                    },
                )
                await click_async(
                    browser, vision_id, use_mouse=True, cursor_policy=cursor_policy
                )
                await browser.page.wait_for_timeout(1200)
                await runtime.record_action("CLICK")
                await runtime.snapshot()
                ok = await apply_verifications(runtime, verify, required)
                if ok:
                    return True, "vision_override_pass"
        if intent_lower == "add_to_cart":
            return ok, "clicked_url_changed" if url_changed else "clicked_no_url_change"
        return ok, "clicked"

    return False, f"unsupported_action:{action}"


async def maybe_run_optional_substeps(
    step: dict[str, Any],
    runtime: AgentRuntime,
    browser: AsyncPredicateBrowser,
    executor: LocalHFModel,
    ctx_formatter: SentienceContext,
    cursor_policy: CursorPolicy,
    vision_llm: Any,
    feedback_path: Path,
    run_id: str,
    step_ok: bool,
    step_note: str | None = None,
) -> None:
    """
    Run optional substeps for a step. Errors are caught and logged but not
    re-raised since these are optional operations.
    """
    try:
        await _run_optional_substeps_impl(
            step, runtime, browser, executor, ctx_formatter, cursor_policy,
            vision_llm, feedback_path, run_id, step_ok, step_note
        )
    except Exception as exc:
        # Log but don't fail - optional substeps should not break the main flow
        exc_type = type(exc).__name__
        print(f"  [optional_substeps] Warning: {exc_type}: {exc}", flush=True)


async def _run_optional_substeps_impl(
    step: dict[str, Any],
    runtime: AgentRuntime,
    browser: AsyncPredicateBrowser,
    executor: LocalHFModel,
    ctx_formatter: SentienceContext,
    cursor_policy: CursorPolicy,
    vision_llm: Any,
    feedback_path: Path,
    run_id: str,
    step_ok: bool,
    step_note: str | None = None,
) -> None:
    """Internal implementation of optional substeps."""
    intent_lower = (step.get("intent") or "").lower()
    optional = step.get("optional_substeps") or []
    if not optional:
        return
    if intent_lower == "add_to_cart":
        if step_ok and step.get("_drawer_handled"):
            return
        if not step_ok:
            fallback = [
                sub
                for sub in optional
                if str(sub.get("action") or "").upper() == "SCROLL"
                or "retry" in str(sub.get("intent") or "").lower()
            ]
            if not fallback:
                return
            for sub in fallback:
                await run_executor_step(
                    sub,
                    runtime,
                    browser,
                    executor,
                    ctx_formatter,
                    cursor_policy,
                    vision_llm,
                    feedback_path,
                    run_id,
                )
            return
        drawer_subs = [
            sub
            for sub in optional
            if str(sub.get("action") or "").upper() != "SCROLL"
            and "retry" not in str(sub.get("intent") or "").lower()
        ]
        # Predicate-driven drawer detection (no text scanning heuristics)
        drawer_visible = await runtime.check(
            any_of(
                exists("text~'Add to Your Order'"),
                exists("text~'No thanks'"),
                exists("text~'Add protection'"),
            ),
            label="drawer_visible",
            required=False,
        ).eventually(timeout_s=3.0, poll_s=0.4, max_snapshot_attempts=4)
        if not drawer_visible:
            return
        if not drawer_subs:
            drawer_subs = [
                {
                    "goal": "Dismiss the add-on drawer by clicking 'No thanks'",
                    "action": "CLICK",
                    "intent": "drawer_no_thanks",
                    "verify": [
                        {
                            "predicate": "not_exists",
                            "args": ["text~'Add to Your Order'"],
                        }
                    ],
                    "required": False,
                }
            ]
        for sub in drawer_subs:
            await run_executor_step(
                sub,
                runtime,
                browser,
                executor,
                ctx_formatter,
                cursor_policy,
                vision_llm,
                feedback_path,
                run_id,
            )
        return
    if intent_lower == "proceed_to_checkout" and not step_ok:
        if not optional:
            optional = [
                {
                    "goal": "Navigate to cart page",
                    "action": "NAVIGATE",
                    "target": "https://www.amazon.com/gp/cart/view.html",
                    "verify": [
                        {
                            "predicate": "any_of",
                            "args": [
                                {"predicate": "url_contains", "args": ["cart"]},
                                {"predicate": "exists", "args": ["text~'Subtotal'"]},
                            ],
                        }
                    ],
                    "required": False,
                },
                {
                    "goal": "Click the 'Proceed to checkout' button",
                    "action": "CLICK",
                    "intent": "proceed_to_checkout",
                    "verify": [
                        {
                            "predicate": "any_of",
                            "args": [
                                {"predicate": "url_contains", "args": ["signin"]},
                                {"predicate": "url_contains", "args": ["/ap/"]},
                                {"predicate": "url_contains", "args": ["checkout"]},
                            ],
                        }
                    ],
                    "required": False,
                    "stop_if_true": True,
                },
            ]
        for sub in optional:
            await run_executor_step(
                sub,
                runtime,
                browser,
                executor,
                ctx_formatter,
                cursor_policy,
                vision_llm,
                feedback_path,
                run_id,
            )
        return
    for sub in optional:
        await run_executor_step(
            sub,
            runtime,
            browser,
            executor,
            ctx_formatter,
            cursor_policy,
            vision_llm,
            feedback_path,
            run_id,
        )

# ---------------------------------------------------------------------------
# PlannerExecutorAgent: Unified orchestrator for Planner + Executor pattern
# ---------------------------------------------------------------------------
class PlannerExecutorAgent:
    """
    Two-tier agent architecture with Planner (7B+) and Executor (3B-7B) models.

    Based on docs/PLANNER_EXECUTOR_DESIGN.md:
    - Planner generates JSON plan with steps and predicates
    - Executor executes each step with snapshot-first approach
    - Supports incremental limit escalation and vision fallback
    - SnapshotContext sharing between planning and execution phases

    Example usage:
        agent = PlannerExecutorAgent(
            planner=LocalHFModel("deepseek-ai/DeepSeek-R1-Distill-Qwen-14B"),
            executor=LocalHFModel("Qwen/Qwen2.5-7B-Instruct"),
            config=PlannerExecutorConfig(),
        )

        async with AsyncPredicateBrowser() as browser:
            runtime = await AgentRuntime.from_browser(browser)
            result = await agent.run(
                runtime=runtime,
                browser=browser,
                task="Search for product and add to cart",
            )
    """

    def __init__(
        self,
        planner: LocalHFModel | LocalMLXModel,
        executor: LocalHFModel | LocalMLXModel,
        config: PlannerExecutorConfig | None = None,
        vision_llm: Any = None,
        ctx_formatter: SentienceContext | None = None,
        cursor_policy: CursorPolicy | None = None,
    ):
        self.planner = planner
        self.executor = executor
        self.config = config or PlannerExecutorConfig()
        self.vision_llm = vision_llm
        self.ctx_formatter = ctx_formatter or SentienceContext(max_elements=120)
        self.cursor_policy = cursor_policy or CursorPolicy(
            mode="human", duration_ms=550, pause_before_click_ms=120, jitter_px=1.5
        )

        # State tracking
        self._current_plan: dict[str, Any] | None = None
        self._step_index: int = 0
        self._replans_used: int = 0
        self._snapshot_context: SnapshotContext | None = None
        self._vision_calls: int = 0

    async def plan(self, task: str, max_attempts: int = 2) -> dict[str, Any]:
        """
        Generate execution plan from task description.

        Returns:
            JSON plan with steps, predicates, and metadata.
        """
        plan, raw_output = extract_plan_with_retry(
            self.planner, task, max_attempts=max_attempts
        )
        errors = validate_plan(plan)
        smoothness = validate_plan_smoothness(plan, task)
        if errors or smoothness:
            combined = errors + smoothness
            raise RuntimeError(
                "Planner output failed validation:\n- " + "\n- ".join(combined)
            )
        self._current_plan = plan
        self._step_index = 0
        return plan

    async def replan(
        self,
        task: str,
        failed_step_id: int | None,
        failure_code: str,
        short_note: str,
        failed_step: dict[str, Any] | None = None,
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        """
        Generate patched plan after step failure.

        Returns:
            Updated plan with failed step modified.
        """
        if self._current_plan is None:
            raise RuntimeError("Cannot replan without an existing plan")

        new_plan, raw_output, mode = extract_replan_with_retry(
            self.planner,
            task,
            current_plan=self._current_plan,
            failed_step_id=failed_step_id,
            failure_code=failure_code,
            short_note=short_note,
            failed_step=failed_step,
            max_attempts=max_attempts,
        )
        self._current_plan = new_plan
        self._replans_used += 1
        return new_plan

    async def snapshot(
        self,
        runtime: AgentRuntime,
        goal: str,
        capture_screenshot: bool = False,
    ) -> SnapshotContext:
        """
        Capture snapshot with limit escalation and vision detection.

        Returns:
            SnapshotContext with snapshot data and vision fallback flags.
        """
        ctx = await snapshot_with_escalation(
            runtime=runtime,
            ctx_formatter=self.ctx_formatter,
            goal=goal,
            config=self.config,
            capture_screenshot=capture_screenshot,
        )
        self._snapshot_context = ctx
        return ctx

    async def execute_step(
        self,
        step: dict[str, Any],
        runtime: AgentRuntime,
        browser: AsyncPredicateBrowser,
        feedback_path: Path,
        run_id: str,
    ) -> tuple[bool, str]:
        """
        Execute a single plan step with vision fallback.

        Returns:
            (success, note) tuple indicating step outcome.
        """
        # Check if we should use vision proactively based on last snapshot
        if (
            self._snapshot_context is not None
            and self._snapshot_context.should_use_vision()
            and self.vision_llm is not None
            and self._vision_calls < self.config.max_vision_calls
        ):
            print(
                f"  [agent] Using vision fallback (reason: {self._snapshot_context.requires_vision})",
                flush=True,
            )
            self._vision_calls += 1

        ok, note = await run_executor_step(
            step=step,
            runtime=runtime,
            browser=browser,
            executor=self.executor,
            ctx_formatter=self.ctx_formatter,
            cursor_policy=self.cursor_policy,
            vision_llm=self.vision_llm,
            feedback_path=feedback_path,
            run_id=run_id,
        )
        return ok, note

    async def verify_step(
        self,
        runtime: AgentRuntime,
        verify: list[dict[str, Any]],
        required: bool,
    ) -> bool:
        """
        Verify step completion with predicate-based assertions.

        Uses incremental limit escalation for required verifications.
        """
        return await apply_verifications(
            runtime=runtime,
            verify=verify,
            required=required,
            config=self.config,
        )

    async def run(
        self,
        runtime: AgentRuntime,
        browser: AsyncPredicateBrowser,
        task: str,
        feedback_path: Path | None = None,
        run_id: str | None = None,
        max_replans: int = 1,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Execute full task with planning, execution, and optional replanning.

        Returns:
            (success, summary) tuple with execution results.
        """
        run_id = run_id or str(uuid.uuid4())
        feedback_path = feedback_path or Path("planner_feedback") / f"{run_id}.jsonl"
        feedback_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate initial plan
        plan = await self.plan(task)
        steps = plan.get("steps", [])
        if not steps:
            return False, {"error": "No steps in plan"}

        print("\n=== PlannerExecutorAgent: Plan Generated ===", flush=True)
        print(json.dumps(plan, indent=2), flush=True)
        print("=== End Plan ===\n", flush=True)

        all_passed = True
        summary = {
            "run_id": run_id,
            "task": task,
            "steps": [],
            "replans_used": 0,
            "success": None,
        }

        step_index = 0
        while step_index < len(steps):
            step = steps[step_index]
            step_start = time.time()

            print(
                f"[Step {step.get('id')}] {step.get('goal')}",
                flush=True,
            )

            ok, note = await self.execute_step(
                step=step,
                runtime=runtime,
                browser=browser,
                feedback_path=feedback_path,
                run_id=run_id,
            )

            # Handle optional substeps
            await maybe_run_optional_substeps(
                step=step,
                runtime=runtime,
                browser=browser,
                executor=self.executor,
                ctx_formatter=self.ctx_formatter,
                cursor_policy=self.cursor_policy,
                vision_llm=self.vision_llm,
                feedback_path=feedback_path,
                run_id=run_id,
                step_ok=ok,
                step_note=note,
            )

            duration_s = round(time.time() - step_start, 3)
            summary["steps"].append({
                "id": step.get("id"),
                "goal": step.get("goal"),
                "success": ok,
                "note": note,
                "duration_s": duration_s,
            })

            print(f"  Result: {'PASS' if ok else 'FAIL'} | {note}", flush=True)

            # Handle failure with replanning
            if not ok and step.get("required", False):
                if self._replans_used < max_replans:
                    try:
                        new_plan = await self.replan(
                            task=task,
                            failed_step_id=step.get("id"),
                            failure_code=str(note),
                            short_note=f"id={step.get('id')} goal={step.get('goal')}",
                            failed_step=step,  # Pass original step to preserve verify predicates
                        )
                        steps = new_plan.get("steps", [])
                        summary["replans_used"] = self._replans_used
                        continue
                    except Exception as exc:
                        print(f"  Replan failed: {exc}", flush=True)
                        all_passed = False
                        break
                else:
                    all_passed = False
                    break

            # Check stop condition
            if step.get("stop_if_true") and ok:
                break

            step_index += 1

        summary["success"] = all_passed
        summary["replans_used"] = self._replans_used
        return all_passed, summary


'''
PLANNER_PROVIDER=mlx \
PLANNER_MODEL=mlx-community/DeepSeek-R1-Distill-Qwen-14B-4bit \
EXECUTOR_PROVIDER=hf \
EXECUTOR_MODEL=Qwen/Qwen2.5-7B-Instruct \
python main.py
'''
async def main() -> None:
    load_dotenv()

    # Default to MLX with 4-bit quantized models for Apple Silicon
    # Qwen 3.5 models (released 2025) - 9B for planner, 4B for executor
    planner_model = os.getenv(
        "PLANNER_MODEL", "mlx-community/Qwen3.5-9B-MLX-4bit"
    )
    executor_model = os.getenv("EXECUTOR_MODEL", "mlx-community/Qwen3.5-4B-MLX-4bit")
    device_map = get_device_map()
    torch_dtype = get_torch_dtype()

    # Default to MLX provider for 4-bit models
    planner_provider = (os.getenv("PLANNER_PROVIDER") or "mlx").lower()
    executor_provider = (os.getenv("EXECUTOR_PROVIDER") or "mlx").lower()
    if planner_provider == "mlx":
        planner = LocalMLXModel(planner_model)
    else:
        planner = LocalHFModel(
            planner_model, device_map=device_map, torch_dtype=torch_dtype
        )
    if executor_provider == "mlx":
        executor = LocalMLXModel(executor_model)
    else:
        executor = LocalHFModel(
            executor_model, device_map=device_map, torch_dtype=torch_dtype
        )

    vision_llm = None
    if os.getenv("ENABLE_VISION_FALLBACK", "0") == "1":
        vision_provider = os.getenv("VISION_PROVIDER", "local").lower()
        vision_model = os.getenv("VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
        if vision_provider == "mlx":
            vision_llm = MLXVLMProvider(model=vision_model)
        else:
            vision_llm = LocalVisionLLMProvider(
                model_name=vision_model, device="auto", torch_dtype="auto"
            )

    predicate_api_key = os.getenv("PREDICATE_API_KEY")
    use_api = bool((predicate_api_key or "").strip())
    run_id = str(uuid.uuid4())
    run_start_ts = time.time()
    feedback_dir = Path(__file__).parent / "planner_feedback"
    feedback_path = feedback_dir / f"{run_id}.jsonl"
    summary_path = feedback_dir / f"{run_id}.summary.json"
    executor_log_path = Path(__file__).parent / "executor.log"

    original_print = builtins.print

    def log_print(*args, **kwargs) -> None:
        original_print(*args, **kwargs)
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args) + end
        with executor_log_path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    tracer = create_tracer(
        api_key=predicate_api_key,
        run_id=run_id,
        upload_trace=True if predicate_api_key else False,
        goal="Amazon planner + executor demo",
        agent_type="planner_executor_local",
        llm_model=f"{planner_model} -> {executor_model}",
        start_url=DEFAULT_PLAN_URL,
    )
    tracer.emit_run_start(
        agent="PlannerExecutorDemo",
        llm_model=planner_model,
        config={
            "snapshot_limit": 50,
            "capture_screenshots": True,
            "show_overlay": True,
            "use_api": bool(use_api),
            "planner_model": planner_model,
            "executor_model": executor_model,
            "search_query": SEARCH_QUERY,
            "max_replans": int(os.getenv("MAX_REPLANS", "1")),
            "planner_mode": os.getenv("PLANNER_MODE", "diet"),
            "vision_fallback": os.getenv("ENABLE_VISION_FALLBACK", "0") == "1",
            "failure_artifacts": {
                "buffer_seconds": 15,
                "capture_on_action": True,
                "fps": 0.0,
                "frame_format": "jpeg",
            },
        },
    )
    builtins.print = log_print
    log_print(f"\n=== Executor Log Start: {run_id} @ {now_iso()} ===", flush=True)

    task = f"Amazon shopping flow: search '{SEARCH_QUERY}', select first product, add to cart, proceed to checkout."
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshots_dir = Path(__file__).parent / "screenshots" / timestamp
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    total_tokens = StepTokenUsage(0, 0, 0)
    step_stats: list[dict[str, Any]] = []
    run_end_emitted = False
    runtime_finalized = False
    runtime = None
    steps: list[dict[str, Any]] = []
    try:
        try:
            plan, raw_plan_output = extract_plan_with_retry(planner, task, max_attempts=2)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse planner JSON: {exc}")
        errors = validate_plan(plan)
        smoothness = validate_plan_smoothness(plan, task)
        if errors or smoothness:
            combined = []
            if errors:
                combined.extend(errors)
            if smoothness:
                combined.extend(smoothness)
            raise RuntimeError(
                "Planner output failed validation:\n- " + "\n- ".join(combined)
            )

        steps = plan.get("steps", [])
        if not steps:
            raise RuntimeError("Planner returned no steps")
        print("\n=== Planner Plan (decision output) ===", flush=True)
        print(json.dumps(plan, indent=2), flush=True)
        print("=== End Planner Plan ===\n", flush=True)
        append_jsonl(
            feedback_path,
            {
                "event": "plan_created",
                "run_id": run_id,
                "model": planner_model,
                "task": task,
                "raw_output": raw_plan_output,
                "plan": plan,
            },
        )

        async with AsyncPredicateBrowser(
            api_key=predicate_api_key, headless=False, user_data_dir=".user_data"
        ) as browser:
            if browser.page is None:
                raise RuntimeError("Browser page not initialized")

            backend = PlaywrightBackend(browser.page)
            runtime = AgentRuntime(
                backend=backend,
                tracer=tracer,
                predicate_api_key=predicate_api_key,
                snapshot_options=SnapshotOptions(
                    limit=50,
                    screenshot=True,
                    show_overlay=True,
                    goal="User planner + executor to buy thinkpad on Amazon.com",
                    use_api=True if use_api else None,
                    predicate_api_key=predicate_api_key if use_api else None,
                ),
            )
            await runtime.enable_failure_artifacts(
                FailureArtifactsOptions(
                    buffer_seconds=15,
                    capture_on_action=True,
                    fps=0.0,
                    frame_format="jpeg",
                )
            )
            runtime.set_captcha_options(
                CaptchaOptions(policy="callback", handler=HumanHandoffSolver())
            )
            ctx_formatter = SentienceContext(max_elements=120)
            cursor_policy = CursorPolicy(
                mode="human", duration_ms=550, pause_before_click_ms=120, jitter_px=1.5
            )

            all_passed = True
            max_replans = int(os.getenv("MAX_REPLANS", "1"))
            replans_used = 0
            step_index = 0
            # Track the last known good URL for recovery after wrong navigation
            last_known_good_url: str | None = None
            summary = {
                "run_id": run_id,
                "task": task,
                "planner_model": planner_model,
                "executor_model": executor_model,
                "start_ts": now_iso(),
                "steps": [],
                "replans_used": 0,
                "success": None,
            }
            while step_index < len(steps):
                step = steps[step_index]
                step_start_ts = time.time()
                step_start_iso = now_iso()
                print(
                    f"[{step_start_iso}] Step {step.get('id')}: {step.get('goal')}",
                    flush=True,
                )
                print("  Planner step decision:", flush=True)
                print(json.dumps(step, indent=2), flush=True)

                # Pre-check: If step verification predicates already pass, skip execution
                # This catches cases where a previous step actually succeeded but was marked as failed
                step_verify = step.get("verify", [])
                if step_verify:
                    pre_check_passed = True
                    for v in step_verify:
                        try:
                            pred = build_predicate(v)
                            pre_ok = runtime.assert_(
                                pred, label="pre_step_check", required=False
                            )
                            if not pre_ok:
                                pre_check_passed = False
                                break
                        except Exception:
                            pre_check_passed = False
                            break
                    if pre_check_passed:
                        print(
                            f"  [skip] Step verification already passes, skipping execution",
                            flush=True,
                        )
                        ok, note = True, "pre_check_passed"
                        step_end_ts = time.time()
                        step_end_iso = now_iso()
                        duration_s = round(step_end_ts - step_start_ts, 3)
                        print(f"  result: {'PASS' if ok else 'FAIL'} | {note}", flush=True)
                        print(f"  step_duration_s: {duration_s}", flush=True)
                        verify_payload = {"assertions": [{"label": "pre_step_check", "passed": True}]}
                        append_jsonl(
                            feedback_path,
                            {
                                "event": "step_result",
                                "run_id": run_id,
                                "step": step,
                                "success": ok,
                                "note": note,
                                "url": browser.page.url if browser.page else "unknown",
                                "assertions": verify_payload,
                                "step_start_ts": step_start_iso,
                                "step_end_ts": step_end_iso,
                                "duration_s": duration_s,
                            },
                        )
                        summary["steps"].append(
                            {
                                "id": step.get("id"),
                                "goal": step.get("goal"),
                                "success": ok,
                                "note": note,
                                "url": browser.page.url if browser.page else "unknown",
                                "step_start_ts": step_start_iso,
                                "step_end_ts": step_end_iso,
                                "duration_s": duration_s,
                            }
                        )
                        if ok:
                            current_url = browser.page.url if browser.page else None
                            if current_url:
                                last_known_good_url = current_url
                        step_index += 1
                        continue

                ok, note = await run_executor_step(
                    step,
                    runtime,
                    browser,
                    executor,
                    ctx_formatter,
                    cursor_policy,
                    vision_llm,
                    feedback_path,
                    run_id,
                )
                step_end_ts = time.time()
                step_end_iso = now_iso()
                duration_s = round(step_end_ts - step_start_ts, 3)
                print(f"  result: {'PASS' if ok else 'FAIL'} | {note}", flush=True)
                print(f"  step_duration_s: {duration_s}", flush=True)
                screenshot_path = (
                    screenshots_dir
                    / f"scene{step.get('id')}_{str(step.get('goal') or '').replace(' ', '_')[:30]}.png"
                )
                try:
                    if browser.page is not None and not browser.page.is_closed():
                        await browser.page.screenshot(path=str(screenshot_path), full_page=False)
                        print(f"  Screenshot saved: {screenshot_path}", flush=True)
                except Exception as exc:
                    print(f"  Warning: Failed to save screenshot: {exc}", flush=True)
                await maybe_run_optional_substeps(
                    step,
                    runtime,
                    browser,
                    executor,
                    ctx_formatter,
                    cursor_policy,
                    vision_llm,
                    feedback_path,
                    run_id,
                    ok,
                    note,
                )
                if (step.get("intent") or "").lower() == "add_to_cart" and not ok:
                    step_verify = step.get("verify", [])
                    step_required = bool(step.get("required", False))
                    try:
                        post_ok = await apply_verifications(runtime, step_verify, step_required)
                    except Exception as exc:
                        post_ok = False
                        print(
                            f"  [warn] post-drawer verify failed: {exc}",
                            flush=True,
                        )
                    if post_ok:
                        ok = True
                        note = "add_to_cart_verified_after_drawer"
                        print(f"  result: PASS | {note}", flush=True)

                verify_payload = runtime.get_assertions_for_step_end()
                llm_usage = getattr(runtime, "_trace_last_llm", {}).get("usage") or {}
                if llm_usage:
                    total_tokens = StepTokenUsage(
                        total_tokens.prompt_tokens
                        + int(llm_usage.get("prompt_tokens") or 0),
                        total_tokens.completion_tokens
                        + int(llm_usage.get("completion_tokens") or 0),
                        total_tokens.total_tokens
                        + int(llm_usage.get("total_tokens") or 0),
                    )
                try:
                    await runtime.emit_step_end(
                        action=str(step.get("action") or "").lower(),
                        success=bool(ok),
                        error=None if ok else str(note or "step_failed"),
                        outcome=str(note or "ok"),
                        verify_passed=bool(ok),
                    )
                except Exception as exc:
                    print(f"  [warn] step_end emit failed: {exc}", flush=True)
                append_jsonl(
                    feedback_path,
                    {
                        "event": "step_result",
                        "run_id": run_id,
                        "step": step,
                        "success": ok,
                        "note": note,
                        "url": browser.page.url if browser.page else "unknown",
                        "assertions": verify_payload,
                        "step_start_ts": step_start_iso,
                        "step_end_ts": step_end_iso,
                        "duration_s": duration_s,
                    },
                )
                summary["steps"].append(
                    {
                        "id": step.get("id"),
                        "goal": step.get("goal"),
                        "success": ok,
                        "note": note,
                        "url": browser.page.url if browser.page else "unknown",
                        "step_start_ts": step_start_iso,
                        "step_end_ts": step_end_iso,
                        "duration_s": duration_s,
                    }
                )
                usage = (
                    StepTokenUsage(
                        int(llm_usage.get("prompt_tokens") or 0),
                        int(llm_usage.get("completion_tokens") or 0),
                        int(llm_usage.get("total_tokens") or 0),
                    )
                    if llm_usage
                    else None
                )
                step_stats.append(
                    {
                        "step_index": step.get("id"),
                        "goal": step.get("goal"),
                        "success": ok,
                        "duration_ms": int(duration_s * 1000),
                        "token_usage": usage,
                    }
                )
                # Track URL after successful steps for recovery
                if ok:
                    current_url = browser.page.url if browser.page else None
                    if current_url:
                        last_known_good_url = current_url

                if not ok and step.get("required", False):
                    if replans_used < max_replans:
                        replans_used += 1
                        summary["replans_used"] = replans_used
                        failure_code = str(note or "unknown_failure")
                        short_note = f"id={step.get('id')} goal={step.get('goal')}"

                        # Recovery: Navigate back to last known good URL if we're on a wrong page
                        # Use the step's verify predicates to detect off-track navigation
                        current_url = browser.page.url if browser.page else ""
                        if last_known_good_url and current_url and current_url != last_known_good_url:
                            # Check if we should recover by verifying we can't satisfy
                            # the step's expected predicates from our current location
                            is_off_track = False
                            off_track_reason = ""
                            failed_predicates: list[str] = []

                            # Get the step's verify predicates and check each one
                            step_verify = step.get("verify", [])
                            for v in step_verify:
                                pred_name = v.get("predicate", "")
                                pred_args = v.get("args", [])

                                # Build predicate and check if it fails
                                if pred_name == "url_contains" and pred_args:
                                    expected_pattern = str(pred_args[0])
                                    pred_ok = runtime.assert_(
                                        url_contains(expected_pattern),
                                        label=f"recovery_check_{pred_name}",
                                        required=False,
                                    )
                                    if not pred_ok:
                                        failed_predicates.append(f"url_contains({expected_pattern})")
                                elif pred_name == "exists" and pred_args:
                                    # Element existence check - if element doesn't exist on wrong page
                                    pred_ok = runtime.assert_(
                                        exists(str(pred_args[0])),
                                        label=f"recovery_check_{pred_name}",
                                        required=False,
                                    )
                                    if not pred_ok:
                                        failed_predicates.append(f"exists({pred_args[0]})")

                            # If any predicate failed and we're on a different URL, we're off-track
                            if failed_predicates:
                                is_off_track = True
                                off_track_reason = f"predicates failed: {', '.join(failed_predicates)}"

                            if is_off_track:
                                print(f"  [recovery] Detected off-track navigation", flush=True)
                                print(f"  [recovery] Reason: {off_track_reason}", flush=True)
                                print(f"  [recovery] Current URL: {current_url[:80]}...", flush=True)
                                print(f"  [recovery] Navigating back to: {last_known_good_url[:80]}...", flush=True)
                                try:
                                    await browser.page.goto(last_known_good_url, timeout=30_000)
                                    await browser.page.wait_for_load_state("domcontentloaded", timeout=15_000)
                                    # Verify we're back by checking the URL changed back
                                    recovered_url = browser.page.url if browser.page else ""
                                    recovery_ok = recovered_url == last_known_good_url or (
                                        last_known_good_url in recovered_url
                                    )
                                    if recovery_ok:
                                        print(f"  [recovery] Successfully navigated back", flush=True)
                                    else:
                                        print(f"  [recovery] Navigation completed but URL differs", flush=True)
                                    append_jsonl(
                                        feedback_path,
                                        {
                                            "event": "recovery_navigation",
                                            "run_id": run_id,
                                            "from_url": current_url,
                                            "to_url": last_known_good_url,
                                            "recovered_url": recovered_url,
                                            "reason": off_track_reason,
                                            "failed_predicates": failed_predicates,
                                            "recovery_verified": bool(recovery_ok),
                                        },
                                    )
                                except Exception as nav_exc:
                                    print(f"  [recovery] Failed to navigate back: {nav_exc}", flush=True)

                        try:
                            new_plan, raw_replan_output, replan_mode = extract_replan_with_retry(
                                planner,
                                task,
                                current_plan=plan,
                                failed_step_id=step.get("id"),
                                failure_code=failure_code,
                                short_note=short_note,
                                failed_step=step,  # Pass the original step to preserve verify predicates
                                max_attempts=2,
                            )
                            if (
                                replan_mode != "patch"
                                and "search_results_not_verified" in failure_code
                            ):
                                new_plan = ensure_minimum_plan(new_plan, SEARCH_QUERY)
                            steps = new_plan.get("steps", [])
                            if not steps:
                                raise RuntimeError("Replan returned no steps")
                            plan = new_plan
                            append_jsonl(
                                feedback_path,
                                {
                                    "event": "replan",
                                    "run_id": run_id,
                                    "model": planner_model,
                                    "failure_code": failure_code,
                                    "note": short_note,
                                    "raw_output": raw_replan_output,
                                    "plan": new_plan,
                                    "mode": replan_mode,
                                },
                            )
                            if replan_mode != "patch":
                                step_index = 0
                            continue
                        except Exception as exc:
                            all_passed = False
                            raise RuntimeError(f"Failed to parse replanned JSON: {exc}")
                    else:
                        all_passed = False
                        break
                if step.get("stop_if_true") and ok:
                    runtime.assert_done(
                        any_of(url_contains("signin"), url_contains("/ap/")),
                        label="checkout_complete",
                    )
                    break
                step_index += 1

            summary["success"] = bool(all_passed)
            summary["end_ts"] = now_iso()
            # Metrics
            durations = [s.get("duration_s", 0) for s in summary["steps"]]
            steps_passed = sum(1 for s in summary["steps"] if s.get("success"))
            steps_failed = sum(
                1 for s in summary["steps"] if s.get("success") is False
            )
            summary["metrics"] = {
                "steps_total": len(summary["steps"]),
                "steps_passed": steps_passed,
                "steps_failed": steps_failed,
                "total_duration_s": round(sum(durations), 3),
                "avg_step_duration_s": (
                    round(sum(durations) / len(durations), 3) if durations else 0
                ),
                "replans_used": summary["replans_used"],
            }
            feedback_dir.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

            run_ms = int((time.time() - run_start_ts) * 1000)
            token_summary = {
                "demo_name": "Planner + Executor Amazon Shopping",
                "total_prompt_tokens": total_tokens.prompt_tokens,
                "total_completion_tokens": total_tokens.completion_tokens,
                "total_tokens": total_tokens.total_tokens,
                "average_per_scene": (
                    total_tokens.total_tokens / len(step_stats) if step_stats else 0
                ),
                "interactions": [
                    {
                        "scene": f"Scene {s['step_index']}: {str(s['goal'])[:40]}",
                        "prompt_tokens": s["token_usage"].prompt_tokens if s["token_usage"] else 0,
                        "completion_tokens": s["token_usage"].completion_tokens if s["token_usage"] else 0,
                        "total": s["token_usage"].total_tokens if s["token_usage"] else 0,
                    }
                    for s in step_stats
                ],
            }
            print("\n=== Run Summary ===", flush=True)
            print(f"run_id: {run_id}", flush=True)
            print(f"success: {all_passed}", flush=True)
            print(f"duration_ms: {run_ms}", flush=True)
            print(f"tokens_total: {total_tokens.total_tokens}", flush=True)
            print(
                f"Steps passed: {sum(1 for s in step_stats if s['success'])}/{len(step_stats)}",
                flush=True,
            )
            video_output = screenshots_dir / "demo.mp4"
            try:
                create_demo_video(str(screenshots_dir), token_summary, str(video_output))
                print(f"✅ Video saved: {video_output}", flush=True)
            except Exception as exc:
                print(f"  Warning: Failed to generate video: {exc}", flush=True)
            runtime.finalize_run(success=all_passed)
            runtime_finalized = True
            tracer.set_final_status("success" if all_passed else "failure")
            tracer.emit_run_end(
                steps=len(steps), status=("success" if all_passed else "failure")
            )
            run_end_emitted = True
            tracer.close(blocking=True)
    finally:
        if not run_end_emitted:
            try:
                tracer.set_final_status("failure")
                tracer.emit_run_end(steps=len(steps), status="failure")
            except Exception:
                pass
        if not runtime_finalized and runtime is not None:
            try:
                runtime.finalize_run(success=False)
            except Exception:
                pass
        try:
            tracer.close(blocking=True)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
