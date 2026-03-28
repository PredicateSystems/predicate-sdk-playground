#!/usr/bin/env python3
"""
Planner + Executor Demo using SDK's Abstracted AutomationTask.

This demo showcases the SDK's PlannerExecutorAgent with:
- AutomationTask for flexible task definition (abstracted WebBenchTask)
- CAPTCHA handling with multiple solver strategies
- Modal/dialog dismissal via heuristic hints
- Recovery and rollback mechanisms
- Custom IntentHeuristics for domain-specific element selection
- Support for both OpenAI and local LLM models

Unlike planner_executor_local (which implements everything from scratch),
this demo uses the SDK's built-in PlannerExecutorAgent and AutomationTask.

Environment variables:
- OPENAI_API_KEY: Required for OpenAI models (when not using --local)
- PLANNER_MODEL: Model for planning (default: gpt-4o or mlx-community/Qwen3-8B-4bit)
- EXECUTOR_MODEL: Model for execution (default: gpt-4o-mini or mlx-community/Qwen3-4B-4bit)
- CAPTCHA_MODE: "abort" | "human" | "external" (default: abort)
- AMAZON_QUERY: Search query (default: laptop)
- HEADLESS: Run browser headless (default: false)
- DEBUG: Enable debug logging (default: false)

Usage:
    # OpenAI models (default)
    python main.py

    # Local MLX models (Apple Silicon)
    python main.py --local

    # Local models with custom model names
    python main.py --local --planner-model mlx-community/Qwen3-8B-4bit --executor-model mlx-community/Qwen3-4B-4bit

    # With human CAPTCHA solving
    CAPTCHA_MODE=human python main.py

    # High-level goal (less defined task)
    python main.py --goal "Find a good laptop deal and add to cart"
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Add SDK to path
sdk_path = Path(__file__).parent.parent.parent / "sdk-python"
sys.path.insert(0, str(sdk_path))

from predicate import AsyncPredicateBrowser, CaptchaOptions
from predicate.agent_runtime import AgentRuntime
from predicate.agents import (
    AutomationTask,
    ComposableHeuristics,
    ExtractionSpec,
    HeuristicHint,
    PlannerExecutorAgent,
    PlannerExecutorConfig,
    RecoveryState,
    SnapshotEscalationConfig,
    StepwisePlanningConfig,
    SuccessCriteria,
    TaskCategory,
    COMMON_HINTS,
    get_common_hint,
)
from predicate.agents.planner_executor_agent import RetryConfig
from predicate.agents.browser_agent import (
    CaptchaConfig,
    PermissionRecoveryConfig,
    VisionFallbackConfig,
)
from predicate.captcha import CaptchaContext, CaptchaResolution
from predicate.captcha_strategies import ExternalSolver, HumanHandoffSolver
from predicate.llm_provider import LLMProvider, LLMResponse, OpenAIProvider
from predicate.tracer_factory import create_tracer
from predicate.tracing import Tracer
from predicate.backends.playwright_backend import PlaywrightBackend
from predicate.backends import PredicateContext
from predicate.models import SnapshotOptions

# Load environment from current working directory (.env file)
# Run from sentience-sdk-playground/ to load the .env file there
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default Local Model Names
# ---------------------------------------------------------------------------
DEFAULT_LOCAL_PLANNER_MODEL = "mlx-community/Qwen3-8B-4bit"
DEFAULT_LOCAL_EXECUTOR_MODEL = "mlx-community/Qwen3-4B-4bit"


# ---------------------------------------------------------------------------
# Local LLM Provider (MLX for Apple Silicon)
# ---------------------------------------------------------------------------


class LocalMLXProvider(LLMProvider):
    """
    Local MLX LLM provider for Apple Silicon.

    Uses mlx-lm for efficient inference on M1/M2/M3/M4 Macs.
    Wraps the SDK's LLMProvider interface for compatibility with PlannerExecutorAgent.
    """

    def __init__(self, model: str):
        """
        Initialize MLX model.

        Args:
            model: Model name (e.g., "mlx-community/Qwen3-8B-4bit")
        """
        super().__init__(model)
        self._model_name_str = model

        try:
            self._mlx_lm = importlib.import_module("mlx_lm")
        except ImportError as exc:
            raise RuntimeError(
                "mlx-lm is required for local MLX models. Install with: pip install mlx-lm"
            ) from exc

        load_fn = getattr(self._mlx_lm, "load", None)
        if not load_fn:
            raise RuntimeError("mlx_lm.load not available in your mlx-lm install.")

        logger.info(f"Loading MLX model: {model}")
        self.model, self.tokenizer = load_fn(model)
        logger.info(f"MLX model loaded: {model}")

    def _build_prompt(self, system: str, user: str) -> str:
        """Build chat prompt using tokenizer's template."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            # Disable thinking mode for Qwen 3 models to get direct JSON output
            kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
            if "qwen3" in self._model_name_str.lower():
                kwargs["enable_thinking"] = False
            return apply_chat_template(messages, **kwargs)
        return f"{system}\n\n{user}"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> LLMResponse:
        """Generate response using MLX model."""
        prompt = self._build_prompt(system_prompt, user_prompt)

        generate_fn = getattr(self._mlx_lm, "generate", None)
        if not generate_fn:
            raise RuntimeError("mlx_lm.generate not available in your mlx-lm install.")

        # Use higher default for planner output (JSON plans can be long)
        max_tokens = kwargs.get("max_tokens", 2048)
        temperature = kwargs.get("temperature", 0.0)

        gen_kwargs: dict[str, Any] = {"max_tokens": max_tokens}

        # Set up sampler for temperature
        if temperature and temperature > 0:
            try:
                sample_utils = importlib.import_module("mlx_lm.sample_utils")
                make_sampler = getattr(sample_utils, "make_sampler", None)
                if callable(make_sampler):
                    gen_kwargs["sampler"] = make_sampler(temp=temperature)
            except Exception:
                pass

        text = generate_fn(
            self.model,
            self.tokenizer,
            prompt,
            **gen_kwargs,
        )

        # Calculate token usage
        try:
            prompt_tokens = len(self.tokenizer.encode(prompt))
            completion_tokens = len(self.tokenizer.encode(text.strip()))
        except Exception:
            prompt_tokens = 0
            completion_tokens = 0

        return LLMResponse(
            content=text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model_name=self._model_name_str,
        )

    def supports_json_mode(self) -> bool:
        """MLX models don't have native JSON mode."""
        return False

    @property
    def model_name(self) -> str:
        """Return model name."""
        return self._model_name_str

    def supports_vision(self) -> bool:
        """Local text models don't support vision."""
        return False


class LocalHFProvider(LLMProvider):
    """
    Local HuggingFace LLM provider using transformers.

    Uses HuggingFace transformers with MPS/CUDA acceleration.
    Wraps the SDK's LLMProvider interface for compatibility with PlannerExecutorAgent.
    """

    def __init__(self, model: str):
        """
        Initialize HuggingFace model.

        Args:
            model: Model name (e.g., "Qwen/Qwen2.5-7B-Instruct")
        """
        super().__init__(model)
        self._model_name_str = model

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "torch and transformers are required for HuggingFace models. "
                "Install with: pip install torch transformers"
            ) from exc

        self._torch = torch

        # Determine device and dtype
        if torch.backends.mps.is_available():
            device_map = "mps"
            torch_dtype = torch.bfloat16
            attn_impl = "sdpa"
        elif torch.cuda.is_available():
            device_map = "auto"
            torch_dtype = torch.float16
            attn_impl = "flash_attention_2"
        else:
            device_map = "cpu"
            torch_dtype = torch.float32
            attn_impl = "eager"

        logger.info(f"Loading HuggingFace model: {model} (device={device_map})")
        self.tokenizer = AutoTokenizer.from_pretrained(model, use_fast=True)

        load_kwargs = {
            "device_map": device_map,
            "torch_dtype": torch_dtype,
            "low_cpu_mem_usage": True,
        }
        if attn_impl != "eager":
            load_kwargs["attn_implementation"] = attn_impl

        self.model = AutoModelForCausalLM.from_pretrained(model, **load_kwargs)
        logger.info(f"HuggingFace model loaded: {model}")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> LLMResponse:
        """Generate response using HuggingFace model."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        encoding = self.tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        )

        device = getattr(self.model, "device", "cpu")
        if hasattr(encoding, "to"):
            encoding = encoding.to(device)

        # Handle different return types from apply_chat_template
        try:
            input_ids = encoding["input_ids"]
            attention_mask = encoding.get("attention_mask")
        except (TypeError, KeyError):
            input_ids = encoding
            attention_mask = None

        input_ids = input_ids.to(device)
        if attention_mask is not None:
            attention_mask = attention_mask.to(device)
        else:
            attention_mask = self._torch.ones_like(input_ids)

        # Use higher default for planner output (JSON plans can be long)
        max_tokens = kwargs.get("max_tokens", 2048)
        temperature = kwargs.get("temperature", 0.0)
        do_sample = temperature > 0

        output_ids = self.model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_tokens,
            do_sample=do_sample,
            temperature=temperature if do_sample else None,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        generated = output_ids[0][input_ids.shape[-1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)

        prompt_tokens = int(input_ids.shape[-1])
        completion_tokens = int(generated.shape[-1])

        return LLMResponse(
            content=text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model_name=self._model_name_str,
        )

    def supports_json_mode(self) -> bool:
        """HuggingFace models don't have native JSON mode."""
        return False

    @property
    def model_name(self) -> str:
        """Return model name."""
        return self._model_name_str

    def supports_vision(self) -> bool:
        """Local text models don't support vision."""
        return False


def create_llm_provider(
    model: str,
    use_local: bool = False,
    provider_type: str = "mlx",
) -> LLMProvider:
    """
    Create an LLM provider based on configuration.

    Args:
        model: Model name
        use_local: Whether to use local models
        provider_type: "mlx" or "hf" for local models

    Returns:
        LLMProvider instance
    """
    if not use_local:
        return OpenAIProvider(model=model)

    if provider_type == "mlx":
        return LocalMLXProvider(model=model)
    elif provider_type == "hf":
        return LocalHFProvider(model=model)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


# ---------------------------------------------------------------------------
# Custom Heuristics for E-commerce Sites
# ---------------------------------------------------------------------------


class EcommerceHeuristics:
    """
    Domain-specific heuristics for e-commerce sites like Amazon.

    These heuristics help the executor find elements without LLM calls
    for common e-commerce patterns.
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        """Find element ID using domain-specific heuristics."""
        intent_lower = intent.lower().replace("-", "_").replace(" ", "_")

        # Search box detection
        if "search" in intent_lower and "box" in intent_lower:
            return self._find_search_box(elements)

        # Add to cart button
        if "add" in intent_lower and "cart" in intent_lower:
            return self._find_add_to_cart(elements)

        # Checkout/proceed button
        if "checkout" in intent_lower or "proceed" in intent_lower:
            return self._find_checkout_button(elements)

        # First product link in search results
        # Match intents like: "first_product_link", "Click on product title", "product link"
        if "product" in intent_lower and ("first" in intent_lower or "link" in intent_lower or "title" in intent_lower):
            return self._find_first_product_link(elements, url)

        # Close/dismiss modal
        if "close" in intent_lower or "dismiss" in intent_lower or "no_thanks" in intent_lower:
            return self._find_dismiss_button(elements)

        # Cookie consent
        if "cookie" in intent_lower or "accept" in intent_lower:
            return self._find_cookie_consent(elements)

        return None

    def priority_order(self) -> list[str]:
        """Return intent patterns in priority order."""
        return [
            "add_to_cart",
            "checkout",
            "proceed_to_checkout",
            "search_box",
            "first_product_link",
            "close",
            "dismiss",
            "no_thanks",
            "accept_cookies",
        ]

    def _find_search_box(self, elements: list[Any]) -> int | None:
        """Find search box element."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"searchbox", "textbox", "combobox"}:
                continue
            text = (getattr(el, "text", "") or "").lower()
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0

            # Prefer elements with "search" in text
            prefers_search = 0 if "search" in text else 1
            candidates.append((not in_viewport, prefers_search, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][4]

    def _find_add_to_cart(self, elements: list[Any]) -> int | None:
        """Find 'Add to Cart' button."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "add to cart" not in text and "add to bag" not in text:
                continue
            if "buy now" in text:
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_checkout_button(self, elements: list[Any]) -> int | None:
        """Find checkout/proceed button."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"button", "link"}:
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "checkout" not in text and "proceed" not in text:
                continue
            # Exclude add to cart and buy now
            if "add to cart" in text or "buy now" in text:
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            is_checkout = 0 if "checkout" in text else 1
            candidates.append((not in_viewport, is_checkout, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][4]

    def _find_first_product_link(self, elements: list[Any], url: str) -> int | None:
        """Find first product link in search results."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "link":
                continue
            href = (getattr(el, "href", "") or "").lower()

            # Must be a product page link
            if "/dp/" not in href and "/gp/product/" not in href:
                continue
            # Exclude filter links
            if "refinements=" in href or "rh=" in href:
                continue

            text = (getattr(el, "text", "") or "").strip()
            # Skip empty or very short text
            if not text or len(text) < 3:
                continue
            # Skip non-product items
            text_lower = text.lower()
            skip_patterns = [
                "sponsored", "free shipping", "prime", "filter", "sort by",
                "see all", "show more"
            ]
            if any(p in text_lower for p in skip_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_dismiss_button(self, elements: list[Any]) -> int | None:
        """Find dismiss/close/no thanks button."""
        candidates = []
        dismiss_patterns = ["no thanks", "close", "dismiss", "cancel", "not now", "skip"]

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if not any(p in text for p in dismiss_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_cookie_consent(self, elements: list[Any]) -> int | None:
        """Find cookie consent accept button."""
        candidates = []
        accept_patterns = ["accept", "accept all", "allow", "agree", "ok", "got it"]

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if not any(p in text for p in accept_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]


# ---------------------------------------------------------------------------
# CAPTCHA Handlers
# ---------------------------------------------------------------------------


def create_captcha_config(mode: str) -> CaptchaConfig:
    """Create CAPTCHA config based on mode."""
    mode = mode.lower()

    if mode == "abort":
        logger.info("CAPTCHA mode: abort (fail on CAPTCHA)")
        return CaptchaConfig(policy="abort", min_confidence=0.7)

    if mode == "human":
        logger.info("CAPTCHA mode: human handoff")
        return CaptchaConfig(
            policy="callback",
            handler=HumanHandoffSolver(
                message="Please solve the CAPTCHA in the browser window",
                timeout_ms=180_000,
                poll_ms=3_000,
            ),
        )

    if mode == "external":
        logger.info("CAPTCHA mode: external solver")

        def external_solver(ctx: CaptchaContext) -> bool:
            """Placeholder for external CAPTCHA solver integration."""
            logger.info(f"CAPTCHA detected at {ctx.url}")
            logger.info(f"Type: {getattr(ctx.captcha, 'type', 'unknown')}")
            logger.info(f"Screenshot: {ctx.screenshot_path}")
            # In production, integrate with 2Captcha, CapSolver, etc.
            # solver = TwoCaptcha('API_KEY')
            # result = solver.recaptcha(sitekey=ctx.captcha.sitekey, url=ctx.url)
            return True

        return CaptchaConfig(
            policy="callback",
            handler=ExternalSolver(
                resolver=external_solver,
                message="Solving CAPTCHA via external service",
                timeout_ms=180_000,
            ),
        )

    # Default to abort
    logger.warning(f"Unknown CAPTCHA mode '{mode}', defaulting to abort")
    return CaptchaConfig(policy="abort")


# ---------------------------------------------------------------------------
# Task Factory
# ---------------------------------------------------------------------------


def create_automation_task(
    goal: str | None = None,
    query: str | None = None,
    starting_url: str = "https://www.amazon.com",
) -> AutomationTask:
    """
    Create an AutomationTask for the demo.

    Args:
        goal: High-level goal (if provided, creates less-defined task)
        query: Search query for Amazon (if provided, creates specific search task)
        starting_url: Starting URL

    Returns:
        AutomationTask instance
    """
    # High-level goal (less defined task)
    if goal:
        logger.info(f"Creating high-level task: {goal}")
        task = AutomationTask(
            task_id=f"goal-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            starting_url=starting_url,
            task=goal,
            category=TaskCategory.TRANSACTION,
            enable_recovery=True,
            max_recovery_attempts=2,
            max_steps=50,
        )
        return task

    # Search task with specific query
    search_query = query or os.getenv("AMAZON_QUERY", "laptop")
    logger.info(f"Creating search task for: {search_query}")

    task = AutomationTask(
        task_id=f"search-{search_query.replace(' ', '-')}-{datetime.now().strftime('%H%M%S')}",
        starting_url=starting_url,
        task=f"Search for '{search_query}' on Amazon, click the first product result, and add it to cart. Then proceed to checkout.",
        category=TaskCategory.TRANSACTION,
        enable_recovery=True,
        max_recovery_attempts=2,
        max_steps=50,
        domain_hints=("ecommerce", "amazon"),
    )

    # Add success criteria
    task = task.with_success_criteria(
        {"predicate": "any_of", "args": [
            {"predicate": "url_contains", "args": ["/cart"]},
            {"predicate": "url_contains", "args": ["checkout"]},
            {"predicate": "url_contains", "args": ["signin"]},
            {"predicate": "url_contains", "args": ["/ap/"]},
        ]},
    )

    return task


# ---------------------------------------------------------------------------
# Main Demo
# ---------------------------------------------------------------------------


async def run_demo(
    goal: str | None = None,
    query: str | None = None,
    starting_url: str = "https://www.amazon.com",
    headless: bool = False,
    use_local: bool = False,
    planner_model: str | None = None,
    executor_model: str | None = None,
    provider_type: str = "mlx",
    stepwise: bool = False,
) -> dict[str, Any]:
    """
    Run the PlannerExecutorAgent demo.

    Args:
        goal: High-level goal for less-defined task
        query: Search query for specific task
        starting_url: Starting URL for the automation
        headless: Run browser in headless mode
        use_local: Use local LLM models instead of OpenAI
        planner_model: Override planner model name
        executor_model: Override executor model name
        provider_type: "mlx" or "hf" for local models
        stepwise: Use stepwise (ReAct-style) planning instead of upfront planning

    Returns:
        Result dictionary with run outcome
    """
    # Determine model names based on mode
    if use_local:
        default_planner = DEFAULT_LOCAL_PLANNER_MODEL
        default_executor = DEFAULT_LOCAL_EXECUTOR_MODEL
    else:
        default_planner = "gpt-4o"
        default_executor = "gpt-4o-mini"

    planner_model = planner_model or os.getenv("PLANNER_MODEL", default_planner)
    executor_model = executor_model or os.getenv("EXECUTOR_MODEL", default_executor)

    # Get Predicate API key for snapshot overlay and cloud features
    predicate_api_key = os.getenv("PREDICATE_API_KEY")
    use_api = bool((predicate_api_key or "").strip())

    logger.info(f"Mode: {'local' if use_local else 'openai'}")
    logger.info(f"Planning: {'stepwise (ReAct)' if stepwise else 'upfront'}")
    logger.info(f"Planner model: {planner_model}")
    logger.info(f"Executor model: {executor_model}")
    logger.info(f"Predicate API: {'enabled' if use_api else 'disabled (no PREDICATE_API_KEY)'}")

    # Create LLM providers
    planner = create_llm_provider(planner_model, use_local, provider_type)
    executor = create_llm_provider(executor_model, use_local, provider_type)

    # Create CAPTCHA config
    captcha_mode = os.getenv("CAPTCHA_MODE", "abort")
    captcha_config = create_captcha_config(captcha_mode)

    # Create agent config
    config = PlannerExecutorConfig(
        # Snapshot escalation for reliable element capture
        snapshot=SnapshotEscalationConfig(
            enabled=True,
            limit_base=60,
            limit_step=30,
            limit_max=200,
        ),
        # Vision fallback for canvas pages
        vision=VisionFallbackConfig(
            enabled=True,
            max_vision_calls=3,
            trigger_requires_vision=True,
            trigger_canvas_or_low_actionables=True,
        ),
        # CAPTCHA handling
        captcha=captcha_config,
        # Retry/verification settings - more lenient for local LLMs
        retry=RetryConfig(
            verify_timeout_s=15.0,  # Increased from 10s
            verify_poll_s=0.5,
            verify_max_attempts=6,  # Increased from 5
            executor_repair_attempts=3,  # Increased from 2
            max_replans=2,  # Allow more replans
        ),
        # LLM settings
        planner_max_tokens=2048,
        planner_temperature=0.0,
        executor_max_tokens=96,
        executor_temperature=0.0,
        # Stabilization
        stabilize_enabled=True,
        stabilize_poll_s=0.35,
        stabilize_max_attempts=6,
        # Pre-step verification
        pre_step_verification=True,
        # Tracing
        trace_screenshots=True,
        # Verbose mode - print plan and executor prompts to stdout
        verbose=True,
        # Stepwise planning config
        stepwise=StepwisePlanningConfig(
            max_steps=30,
            action_history_limit=5,
            include_page_context=True,
        ),
    )

    # Create tracer
    tracer = create_tracer(
        goal=goal or f"Amazon search: {query or os.getenv('AMAZON_QUERY', 'laptop')}",
        agent_type="PlannerExecutorAgent",
    )

    # Create context formatter (same as planner_executor_local)
    ctx_formatter = PredicateContext(max_elements=120)

    # Wrap the context formatter to match expected signature (snap, goal) -> str
    def format_context(snap, goal):
        return ctx_formatter._format_snapshot_for_llm(snap)

    # Create agent with custom heuristics and context formatter
    agent = PlannerExecutorAgent(
        planner=planner,
        executor=executor,
        config=config,
        tracer=tracer,
        intent_heuristics=EcommerceHeuristics(),
        context_formatter=format_context,
    )

    # Create automation task
    task = create_automation_task(goal=goal, query=query, starting_url=starting_url)

    logger.info("=" * 60)
    logger.info("Starting PlannerExecutorAgent Demo")
    logger.info("=" * 60)
    logger.info(f"Task ID: {task.task_id}")
    logger.info(f"Task: {task.task}")
    logger.info(f"Starting URL: {task.starting_url}")
    logger.info(f"Category: {task.category}")
    logger.info(f"Recovery enabled: {task.enable_recovery}")
    logger.info("=" * 60)

    # Run automation
    # Grant common permissions to avoid browser permission prompts during automation.
    # Supported permissions (may vary by browser version):
    # - geolocation: store locators, local inventory
    # - notifications: push notification prompts
    # - clipboard-read/write: copy/paste functionality
    # See: https://playwright.dev/python/docs/api/class-browsercontext#browser-context-grant-permissions
    permission_policy = {
        "auto_grant": [
            "geolocation",
            "notifications",
            "clipboard-read",
            "clipboard-write",
        ],
        "geolocation": {"latitude": 47.6762, "longitude": -122.2057},  # Kirkland, WA
    }
    async with AsyncPredicateBrowser(
        api_key=predicate_api_key,
        headless=headless,
        permission_policy=permission_policy,
    ) as browser:
        # AsyncSentienceBrowser creates a page in start() and stores it in browser.page
        page = browser.page
        await page.goto(task.starting_url)
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        # Wait for network to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass  # Best effort
        # Extra wait for extension to initialize
        await page.wait_for_timeout(1000)

        # Create runtime using PlaywrightBackend (same as planner_executor_local)
        backend = PlaywrightBackend(page)
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            predicate_api_key=predicate_api_key,
            snapshot_options=SnapshotOptions(
                limit=60,
                screenshot=True,
                show_overlay=True,
                goal=task.task,
                use_api=True if use_api else None,
                predicate_api_key=predicate_api_key if use_api else None,
            ),
        )

        try:
            # Use stepwise or upfront planning based on flag
            if stepwise:
                result = await agent.run_stepwise(runtime, task)
            else:
                result = await agent.run(runtime, task)

            logger.info("=" * 60)
            logger.info("Run Complete")
            logger.info("=" * 60)
            logger.info(f"Success: {result.success}")
            logger.info(f"Steps completed: {result.steps_completed}/{result.steps_total}")
            logger.info(f"Replans used: {result.replans_used}")
            logger.info(f"Duration: {result.total_duration_ms}ms")

            if result.error:
                logger.error(f"Error: {result.error}")

            # Log step outcomes
            for outcome in result.step_outcomes:
                status = "OK" if outcome.verification_passed else "FAIL"
                vision = " [vision]" if outcome.used_vision else ""
                logger.info(
                    f"  Step {outcome.step_id}: {outcome.goal[:50]}... "
                    f"- {status}{vision}"
                )

            return {
                "success": result.success,
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "replans_used": result.replans_used,
                "duration_ms": result.total_duration_ms,
                "error": result.error,
            }

        except Exception as e:
            logger.exception(f"Demo failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }
        finally:
            tracer.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PlannerExecutorAgent Demo with SDK's AutomationTask"
    )
    parser.add_argument(
        "--goal",
        type=str,
        help="High-level goal for less-defined task (e.g., 'Find a good laptop deal')",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Search query for Amazon (e.g., 'wireless mouse')",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://www.amazon.com",
        help="Starting URL (default: https://www.amazon.com)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.getenv("HEADLESS", "").lower() in {"1", "true", "yes"},
        help="Run browser in headless mode",
    )

    # LLM provider options
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local LLM models instead of OpenAI (default: MLX on Apple Silicon)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["mlx", "hf"],
        default="mlx",
        help="Local model provider: 'mlx' (Apple Silicon) or 'hf' (HuggingFace transformers)",
    )
    parser.add_argument(
        "--planner-model",
        type=str,
        help=f"Planner model name (default: gpt-4o or {DEFAULT_LOCAL_PLANNER_MODEL} for local)",
    )
    parser.add_argument(
        "--executor-model",
        type=str,
        help=f"Executor model name (default: gpt-4o-mini or {DEFAULT_LOCAL_EXECUTOR_MODEL} for local)",
    )
    parser.add_argument(
        "--stepwise",
        action="store_true",
        help="Use stepwise (ReAct-style) planning instead of upfront planning",
    )

    args = parser.parse_args()

    # Check for API key if using OpenAI
    if not args.local and not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "OPENAI_API_KEY environment variable is required when not using --local.\n"
            "Either set OPENAI_API_KEY or use --local for local models."
        )
        sys.exit(1)

    # Run the demo
    result = asyncio.run(run_demo(
        goal=args.goal,
        query=args.query,
        starting_url=args.url,
        headless=args.headless,
        use_local=args.local,
        planner_model=args.planner_model,
        executor_model=args.executor_model,
        provider_type=args.provider,
        stepwise=args.stepwise,
    ))

    # Exit with appropriate code
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
