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
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer

from sentience.actions import click_async, press_async
from sentience.agent_runtime import AgentRuntime
from sentience.async_api import AsyncSentienceBrowser
from sentience.backends.playwright_backend import PlaywrightBackend
from sentience.backends.sentience_context import SentienceContext
from sentience.cursor_policy import CursorPolicy
from sentience.llm_provider import LocalVisionLLMProvider, MLXVLMProvider
from sentience.models import SnapshotOptions
from sentience.tracer_factory import create_tracer
from sentience.verification import (
    all_of,
    any_of,
    custom,
    element_count,
    exists,
    not_exists,
    url_contains,
    url_matches,
)


SEARCH_QUERY = os.getenv("AMAZON_QUERY", "laptop")
DEFAULT_PLAN_URL = "https://www.amazon.com"


@dataclass
class LlmResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


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
    # Use "auto" for better layer distribution on MPS (Apple Silicon)
    # This allows transformers to automatically distribute layers across unified memory
    if torch.backends.mps.is_available():
        return "auto"
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
            "torch_dtype": torch_dtype,
            "low_cpu_mem_usage": True,  # Better memory management for large models
        }

        # MPS-specific optimizations for Apple Silicon (M1/M2/M3/M4)
        if torch.backends.mps.is_available():
            # MPS doesn't support flash attention - use eager or sdpa
            # eager is more stable on MPS but sdpa is faster if available
            load_kwargs["attn_implementation"] = "sdpa"  # Scaled Dot Product Attention
            # Note: If you encounter errors, fallback to "eager"
            # load_kwargs["attn_implementation"] = "eager"

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            **load_kwargs
        )

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
        input_ids = self.tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        )
        device = getattr(self.model, "device", "cpu")
        input_ids = input_ids.to(device)
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


def extract_json(text: str) -> dict[str, Any]:
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


def build_planner_prompt(task: str, strict: bool = False) -> tuple[str, str]:
    system = (
        "You are the PLANNER. Output a JSON plan for an Executor to run.\n"
        "The Executor can only click/type using element IDs from snapshots.\n"
        "Include explicit verification predicates per step.\n"
        "Use stop_if_true for sign-in redirect after checkout.\n"
        "If a soft-block page appears on Amazon with a 'Click to Continue' button, "
        "include an optional substep to detect and click it.\n"
        "Do NOT hardcode product URLs like /dp/product-url; use a CLICK step on the first product link."
    )
    strict_note = (
        "\nReturn ONLY a JSON object. Do not include any other text.\n"
        if strict
        else ""
    )
    user = f"""
Task: {task}
{strict_note}

Output JSON with fields:
- task: string
- notes: list of strings
- steps: list of steps (id, goal, action, target/intent/input, verify, required, stop_if_true?, optional_substeps?)

Predicates allowed: url_contains, url_matches, exists, not_exists, element_count, any_of, all_of.
Note: url_contains expects a single string; use any_of for multiple options.

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
      "required": true,
      "optional_substeps": [
        {{
          "id": 1,
          "goal": "If soft-block appears, click 'Click to Continue'",
          "action": "CLICK",
          "intent": "soft_block_continue",
          "verify": [{{ "predicate": "not_exists", "args": ["text~'Click to Continue'"] }}],
          "required": false
        }}
      ]
    }},
    {{
      "id": 2,
      "goal": "Focus the search box",
      "action": "CLICK",
      "intent": "search_box",
      "verify": [{{ "predicate": "exists", "args": ["role=textbox"] }}],
      "required": true
    }},
    {{
      "id": 3,
      "goal": "Type search query with human-like jitter and submit",
      "action": "TYPE_AND_SUBMIT",
      "input": "laptop",
      "verify": [{{ "predicate": "url_contains", "args": ["k=laptop"] }}],
      "required": true
    }},
    {{
      "id": 4,
      "goal": "Click the FIRST product link in search results",
      "action": "CLICK",
      "intent": "first_product_link",
      "verify": [{{ "predicate": "url_contains", "args": ["/dp/"] }}],
      "required": true
    }},
    {{
      "id": 5,
      "goal": "Add product to cart and handle optional drawer",
      "action": "CLICK",
      "intent": "add_to_cart",
      "verify": [
        {{ "predicate": "any_of", "args": [
          {{ "predicate": "exists", "args": ["text~'Added to Cart'"] }},
          {{ "predicate": "url_contains", "args": ["cart"] }}
        ]}}
      ],
      "required": true,
      "optional_substeps": [
        {{
          "goal": "If 'Add to Your Order' drawer appears, click 'No thanks'",
          "action": "CLICK",
          "intent": "drawer_no_thanks",
          "verify": [{{ "predicate": "not_exists", "args": ["text~'Add to Your Order'"] }}],
          "required": false
        }}
      ]
    }},
    {{
      "id": 6,
      "goal": "Proceed to checkout",
      "action": "CLICK",
      "intent": "proceed_to_checkout",
      "verify": [{{ "predicate": "any_of", "args": [
        {{ "predicate": "url_contains", "args": ["signin"] }},
        {{ "predicate": "url_contains", "args": ["/ap/"] }}
      ]}}],
      "required": false,
      "stop_if_true": true
    }}
  ]
}}
"""
    return system, user


def extract_plan_with_retry(
    planner: LocalHFModel, task: str, max_attempts: int = 2
) -> tuple[dict[str, Any], str]:
    last_output = ""
    for attempt in range(1, max_attempts + 1):
        max_tokens = 1024 if attempt == 1 else 1536
        sys_prompt, user_prompt = build_planner_prompt(task, strict=(attempt > 1))
        resp = planner.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=max_tokens
        )
        last_output = resp.content
        try:
            plan = extract_json(resp.content)
            plan = normalize_plan(plan)
            return plan, last_output
        except Exception:
            continue
    raise RuntimeError(
        f"Planner failed to return JSON after {max_attempts} attempts.\nRaw output:\n{last_output}"
    )


def build_replan_prompt(
    task: str,
    feedback: str,
    strict: bool = False,
    schema_errors: str | None = None,
) -> tuple[str, str]:
    system = (
        "You are the PLANNER. Output a JSON plan for an Executor to run.\n"
        "Keep the same JSON format as the original plan.\n"
        "Only include the remaining steps from the current point onward.\n"
        "Do not include any extra keys beyond the schema.\n"
        "Actions must be one of: NAVIGATE, CLICK, TYPE_AND_SUBMIT.\n"
        "Step ids in a replan MUST start at 1 and be contiguous.\n"
        "Do NOT hardcode product URLs like /dp/product-url; use CLICK on a product link."
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
    user = f"""
Task: {task}
{strict_note}

Execution feedback:
{feedback}
{schema_note}

Return a revised JSON plan for the remaining steps only.

Format example (match keys exactly):
{{
  "task": "Amazon shopping cart checkout flow",
  "notes": ["Use snapshot IDs only"],
  "steps": [
    {{
      "id": 1,
      "goal": "Focus the search box",
      "action": "CLICK",
      "intent": "search_box",
      "verify": [{{ "predicate": "exists", "args": ["role=textbox"] }}],
      "required": true
    }},
    {{
      "id": 2,
      "goal": "Type search query with human-like jitter and submit",
      "action": "TYPE_AND_SUBMIT",
      "input": "laptop",
      "verify": [{{ "predicate": "url_contains", "args": ["k=laptop"] }}],
      "required": true
    }}
  ]
}}
"""
    return system, user


def extract_replan_with_retry(
    planner: LocalHFModel,
    task: str,
    feedback: str,
    max_attempts: int = 2,
) -> tuple[dict[str, Any], str]:
    last_output = ""
    last_errors = ""
    for attempt in range(1, max_attempts + 1):
        max_tokens = 768 if attempt == 1 else 1024
        sys_prompt, user_prompt = build_replan_prompt(
            task, feedback, strict=(attempt > 1), schema_errors=last_errors or None
        )
        resp = planner.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=max_tokens
        )
        last_output = resp.content
        try:
            plan = extract_json(resp.content)
            plan = normalize_plan(plan)
            errors = validate_plan(plan)
            if errors:
                last_errors = "\n".join(f"- {e}" for e in errors)
                continue
            return plan, last_output
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
            "2) Ignore menu items or top nav links (e.g., 'Amazon Haul').\n"
            "3) Do NOT follow high importance alone; prioritize ordinality in the dominant group (DG=1, ord=0).\n"
            "4) If multiple matches, choose the FIRST product link in the main results list.\n\n"
        )
    user = (
        "You are controlling a browser via element IDs.\n\n"
        "You must respond with exactly ONE action in this format:\n"
        "- CLICK(<id>)\n\n"
        f"Goal: {goal}\n"
        f"{intent_line}"
        f"{extra_rules}"
        "SNAPSHOT FORMAT: ID|role|text|imp|is_primary|docYq|ord|DG|href\n\n"
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


async def get_page_screenshot_base64(browser: AsyncSentienceBrowser) -> str:
    png_bytes = await browser.page.screenshot(full_page=False)
    return base64.b64encode(png_bytes).decode("ascii")


async def vision_fallback_check(
    *,
    vision_llm: Any,
    browser: AsyncSentienceBrowser,
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
    browser: AsyncSentienceBrowser,
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
        "Snapshot list (ID|role|text|imp|is_primary|docYq|ord|DG|href):\n"
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
    runtime: AgentRuntime, verify: list[dict[str, Any]], required: bool
) -> bool:
    if not verify:
        return True
    ok_all = True
    for idx, v in enumerate(verify, start=1):
        pred = build_predicate(v)
        label = v.get("label") or f"verify_{idx}"
        if required:
            ok = await runtime.check(pred, label=label, required=True).eventually(
                timeout_s=8.0, poll_s=0.5, max_snapshot_attempts=8
            )
        else:
            ok = runtime.assert_(pred, label=label, required=False)
        ok_all = ok_all and bool(ok)
    return ok_all


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
    allowed_actions = {"NAVIGATE", "CLICK", "TYPE_AND_SUBMIT"}
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
        extra_keys = set(step.keys()) - allowed_step_keys
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
                    extra = set(sub.keys()) - allowed_step_keys
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
            "goal": "Add product to cart and handle optional drawer",
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
                }
            ],
        },
        {
            "id": 5,
            "goal": "Proceed to checkout",
            "action": "CLICK",
            "intent": "proceed_to_checkout",
            "verify": [
                {
                    "predicate": "any_of",
                    "args": [
                        {"predicate": "url_contains", "args": ["signin"]},
                        {"predicate": "url_contains", "args": ["/ap/"]},
                    ],
                }
            ],
            "required": False,
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
    browser: AsyncSentienceBrowser,
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

    if action == "NAVIGATE":
        target = step.get("target", DEFAULT_PLAN_URL)
        await browser.goto(target)
        await browser.page.wait_for_load_state("domcontentloaded", timeout=15_000)
        snap = await runtime.snapshot()
        if snap is not None:
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            print("\n--- Compact prompt (snapshot) ---", flush=True)
            print(compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
        return ok, "navigated"

    if action == "TYPE_AND_SUBMIT":
        # Ensure search box is focused before typing
        pre_snap = await runtime.snapshot(
            limit=60, screenshot=False, goal="Focus search box before typing"
        )
        if pre_snap is not None:
            pre_compact = ctx_formatter._format_snapshot_for_llm(pre_snap)
            print("\n--- Compact prompt (pre-type snapshot) ---", flush=True)
            print(pre_compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
            focus_goal = "Click the search input box (role=searchbox or role=textbox) before typing."
            sys_prompt, user_prompt = build_executor_prompt(
                focus_goal, "search_box", pre_compact
            )
            focus_resp = executor.generate(
                sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24
            )
            focus_id = parse_click_id(focus_resp.content)
            if focus_id is not None:
                await click_async(
                    browser, focus_id, use_mouse=True, cursor_policy=cursor_policy
                )
                await browser.page.wait_for_timeout(400)

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
            limit=120, screenshot=False, goal="Search results snapshot"
        )
        if snap is not None:
            compact = ctx_formatter._format_snapshot_for_llm(snap)
            print("\n--- Compact prompt (snapshot) ---", flush=True)
            print(compact, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
        return ok, "typed_and_submitted"

    if action == "CLICK":
        intent_lower = (intent or "").lower()
        snap_limit = (
            120
            if intent_lower
            in {"search_box", "first_product_link", "first_search_result"}
            else 60
        )
        if intent_lower in {"first_product_link", "first_search_result"}:

            def _has_product_links(ctx) -> bool:
                snap = ctx.snapshot
                if not snap:
                    return False
                return any(
                    (el.href or "").find("/dp/") >= 0
                    or (el.href or "").find("/gp/product/") >= 0
                    for el in snap.elements
                )

            links_ok = await runtime.check(
                custom(_has_product_links, label="product_links_present"),
                label="product_links_present",
                required=True,
            ).eventually(timeout_s=12.0, poll_s=0.5, max_snapshot_attempts=12)
            if not links_ok:
                return False, "product_links_not_found"
            snap_limit = 160
        snap = await runtime.snapshot(limit=snap_limit, screenshot=False, goal=goal)
        if snap is None:
            return False, "snapshot_missing"
        compact = ctx_formatter._format_snapshot_for_llm(snap)
        print("\n--- Compact prompt (snapshot) ---", flush=True)
        print(compact, flush=True)
        print("--- end compact prompt ---\n", flush=True)
        sys_prompt, user_prompt = build_executor_prompt(goal, intent, compact)
        resp = executor.generate(
            sys_prompt, user_prompt, temperature=0.0, max_new_tokens=24
        )
        click_id = parse_click_id(resp.content)
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
        await click_async(
            browser, click_id, use_mouse=True, cursor_policy=cursor_policy
        )
        await browser.page.wait_for_timeout(1200)
        snap_after = await runtime.snapshot()
        compact_after = None
        if snap_after is not None:
            compact_after = ctx_formatter._format_snapshot_for_llm(snap_after)
            print("\n--- Compact prompt (post-click snapshot) ---", flush=True)
            print(compact_after, flush=True)
            print("--- end compact prompt ---\n", flush=True)
        ok = await apply_verifications(runtime, verify, required)
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
                await runtime.snapshot()
                ok = await apply_verifications(runtime, verify, required)
                if ok:
                    return True, "vision_override_pass"
        return ok, "clicked"

    return False, f"unsupported_action:{action}"


async def maybe_run_optional_substeps(
    step: dict[str, Any],
    runtime: AgentRuntime,
    browser: AsyncSentienceBrowser,
    executor: LocalHFModel,
    ctx_formatter: SentienceContext,
    cursor_policy: CursorPolicy,
    vision_llm: Any,
    feedback_path: Path,
    run_id: str,
) -> None:
    optional = step.get("optional_substeps") or []
    if not optional:
        return
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


async def main() -> None:
    load_dotenv()

    planner_model = os.getenv("PLANNER_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    executor_model = os.getenv("EXECUTOR_MODEL", "Qwen/Qwen2.5-3B-Instruct")
    device_map = get_device_map()
    torch_dtype = get_torch_dtype()

    planner = LocalHFModel(
        planner_model, device_map=device_map, torch_dtype=torch_dtype
    )
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

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")
    use_api = bool((sentience_api_key or "").strip())
    run_id = str(uuid.uuid4())
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
        api_key=sentience_api_key,
        run_id=run_id,
        upload_trace=bool(sentience_api_key),
        goal="Amazon planner + executor demo",
        agent_type="planner_executor_local",
        llm_model=f"{planner_model} -> {executor_model}",
        start_url=DEFAULT_PLAN_URL,
    )
    tracer.emit_run_start(
        agent="PlannerExecutorDemo", llm_model=planner_model, config={}
    )
    builtins.print = log_print
    log_print(f"\n=== Executor Log Start: {run_id} @ {now_iso()} ===", flush=True)

    task = f"Amazon shopping flow: search '{SEARCH_QUERY}', select first product, add to cart, proceed to checkout."
    try:
        plan, raw_plan_output = extract_plan_with_retry(planner, task, max_attempts=2)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse planner JSON: {exc}")
    errors = validate_plan(plan)
    if errors:
        raise RuntimeError(
            "Planner output failed schema validation:\n- " + "\n- ".join(errors)
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

    async with AsyncSentienceBrowser(
        headless=False, user_data_dir=".user_data"
    ) as browser:
        if browser.page is None:
            raise RuntimeError("Browser page not initialized")

        backend = PlaywrightBackend(browser.page)
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key=sentience_api_key,
            snapshot_options=SnapshotOptions(
                limit=60,
                screenshot=False,
                show_overlay=True,
                goal="Amazon planner executor flow",
                use_api=True if use_api else None,
                sentience_api_key=sentience_api_key if use_api else None,
            ),
        )
        ctx_formatter = SentienceContext(max_elements=120)
        cursor_policy = CursorPolicy(
            mode="human", duration_ms=550, pause_before_click_ms=120, jitter_px=1.5
        )

        all_passed = True
        max_replans = int(os.getenv("MAX_REPLANS", "1"))
        replans_used = 0
        step_index = 0
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
            )

            verify_payload = runtime.get_assertions_for_step_end()
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
            if not ok and step.get("required", False):
                if replans_used < max_replans:
                    replans_used += 1
                    summary["replans_used"] = replans_used
                    feedback = (
                        f"Step failed: id={step.get('id')}, goal={step.get('goal')}\n"
                        f"URL: {browser.page.url if browser.page else 'unknown'}\n"
                        f"Note: {note}\n"
                        f"Assertions: {json.dumps(verify_payload, indent=2)}\n"
                    )
                    try:
                        new_plan, raw_replan_output = extract_replan_with_retry(
                            planner, task, feedback, max_attempts=2
                        )
                        if "search_results_not_verified" in feedback:
                            new_plan = ensure_minimum_plan(new_plan, SEARCH_QUERY)
                        steps = new_plan.get("steps", [])
                        if not steps:
                            raise RuntimeError("Replan returned no steps")
                        append_jsonl(
                            feedback_path,
                            {
                                "event": "replan",
                                "run_id": run_id,
                                "model": planner_model,
                                "feedback": feedback,
                                "raw_output": raw_replan_output,
                                "plan": new_plan,
                            },
                        )
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
        steps_failed = sum(1 for s in summary["steps"] if s.get("success") is False)
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

        tracer.set_final_status("success" if all_passed else "failure")
        tracer.emit_run_end(
            steps=len(steps), status=("success" if all_passed else "failure")
        )
        tracer.close(blocking=True)


if __name__ == "__main__":
    asyncio.run(main())
