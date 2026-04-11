#!/usr/bin/env python3
"""
Generic Browser Agent Demo using SDK's PlannerExecutorAgent.

This demo showcases browser automation with the Predicate SDK's PlannerExecutorAgent,
supporting multiple LLM providers and task categories from WebBench.

FEATURES:
---------
- Multiple LLM provider backends (OpenAI, DeepInfra, Ollama, MLX, HuggingFace)
- Pre-defined task templates for shopping, search, forms, travel
- Custom task support via natural language
- Domain-specific heuristics for faster element selection
- Recovery and replan mechanisms
- Vision fallback for complex pages

PROVIDERS:
----------
- openai: GPT-4o / GPT-4o-mini (requires OPENAI_API_KEY)
- deepinfra: Qwen 27B / 9B via DeepInfra API (requires DEEPINFRA_API_KEY)
- ollama: Local models via Ollama (requires Ollama running locally)
- mlx: Apple Silicon optimized models via mlx-lm
- huggingface: HuggingFace Transformers (torch/transformers)

USAGE EXAMPLES:
---------------
# Run with OpenAI (default)
python main.py --task "Search for laptop on Amazon and add to cart"

# Run with DeepInfra (Qwen models)
python main.py --provider deepinfra --task "Search for laptop on Amazon"

# Run with local Ollama models
python main.py --provider ollama --planner-model qwen2.5:14b --executor-model qwen2.5:7b

# Run with MLX models on Apple Silicon
python main.py --provider mlx

# Run a pre-defined task template
python main.py --template amazon_search_add_to_cart

# Custom starting URL
python main.py --url https://bestbuy.com --task "Find the cheapest 4K TV"

# Headless mode
python main.py --headless --task "Extract top 5 Hacker News headlines"

ENVIRONMENT VARIABLES:
----------------------
- OPENAI_API_KEY: Required for OpenAI provider
- DEEPINFRA_API_KEY: Required for DeepInfra provider
- PREDICATE_API_KEY: Optional, enables cloud features (overlay, tracing)
- DEBUG: Set to "1" for verbose logging
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add SDK to path
sdk_path = Path(__file__).parent.parent.parent / "sdk-python"
sys.path.insert(0, str(sdk_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Local imports
from task_definitions import (
    ALL_TASKS,
    TaskCategory,
    TaskDefinition,
    create_custom_task,
    get_task,
    list_tasks,
)
from providers import (
    ProviderType,
    create_planner_executor_providers,
)
from heuristics import get_heuristics_for_domain
from overlay_utils import dismiss_overlays_before_agent

# SDK imports
from predicate import AsyncPredicateBrowser
from predicate.agent_runtime import AgentRuntime
from predicate.agents import (
    AutomationTask,
    PlannerExecutorAgent,
    PlannerExecutorConfig,
    SnapshotEscalationConfig,
    SuccessCriteria,
    TaskCategory as SdkTaskCategory,
)
from predicate.agents.planner_executor_agent import RetryConfig
from predicate.agents.browser_agent import VisionFallbackConfig
from predicate.backends.playwright_backend import PlaywrightBackend
from predicate.models import SnapshotOptions
from predicate.tracer_factory import create_tracer

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def format_compact_token_summary(token_stats: dict[str, Any]) -> str:
    """Return a compact per-role token summary string."""
    by_role = token_stats.get("by_role", {}) if isinstance(token_stats, dict) else {}
    ordered_roles = ("planner", "extract", "executor", "replan", "vision")
    parts: list[str] = []

    for role in ordered_roles:
        role_stats = by_role.get(role) or {}
        total_tokens = int(role_stats.get("total_tokens", 0) or 0)
        if total_tokens > 0:
            parts.append(f"{role}={total_tokens}")

    for role, role_stats in by_role.items():
        if role in ordered_roles:
            continue
        total_tokens = int((role_stats or {}).get("total_tokens", 0) or 0)
        if total_tokens > 0:
            parts.append(f"{role}={total_tokens}")

    return ", ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser with comprehensive CLI options."""
    p = argparse.ArgumentParser(
        prog="generic_browser_agent_demo",
        description="Generic Browser Agent Demo using SDK's PlannerExecutorAgent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Run with OpenAI
  python main.py --task "Search for wireless mouse on Amazon and add to cart"

  # Run with DeepInfra Qwen models
  python main.py --provider deepinfra --task "Find laptop deals on BestBuy"

  # Run with local Ollama
  python main.py --provider ollama --planner-model qwen2.5:14b --task "Search Wikipedia for AI"

  # Run a pre-defined template
  python main.py --template lifeisgood_shopping

  # List available templates
  python main.py --list-templates
""",
    )

    # ==========================================================================
    # Task specification
    # ==========================================================================
    task_group = p.add_argument_group("Task Options")
    task_group.add_argument(
        "--task",
        type=str,
        help="Natural language task description",
    )
    task_group.add_argument(
        "--url",
        type=str,
        default=None,
        help="Starting URL for the automation",
    )
    task_group.add_argument(
        "--template",
        type=str,
        default=None,
        help="Use a pre-defined task template (see --list-templates)",
    )
    task_group.add_argument(
        "--list-templates",
        action="store_true",
        help="List all available task templates and exit",
    )
    task_group.add_argument(
        "--category",
        type=str,
        choices=["read", "create", "update", "delete", "transaction"],
        default="transaction",
        help="Task category (default: transaction)",
    )

    # ==========================================================================
    # LLM Provider configuration
    # ==========================================================================
    provider_group = p.add_argument_group("LLM Provider Options")
    provider_group.add_argument(
        "--provider",
        type=str,
        choices=["openai", "deepinfra", "ollama", "mlx", "huggingface", "hf"],
        default="openai",
        help="LLM provider backend (default: openai)",
    )
    provider_group.add_argument(
        "--planner-provider",
        type=str,
        choices=["openai", "deepinfra", "ollama", "mlx", "huggingface"],
        default=None,
        help="Override provider for planner model",
    )
    provider_group.add_argument(
        "--executor-provider",
        type=str,
        choices=["openai", "deepinfra", "ollama", "mlx", "huggingface"],
        default=None,
        help="Override provider for executor model",
    )
    provider_group.add_argument(
        "--planner-model",
        type=str,
        default=None,
        help="Override planner model name (e.g., gpt-4o, qwen2.5:14b)",
    )
    provider_group.add_argument(
        "--executor-model",
        type=str,
        default=None,
        help="Override executor model name (e.g., gpt-4o-mini, qwen2.5:7b)",
    )

    # ==========================================================================
    # Browser options
    # ==========================================================================
    browser_group = p.add_argument_group("Browser Options")
    browser_group.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode",
    )
    browser_group.add_argument(
        "--no-headless",
        action="store_true",
        default=False,
        help="Force visible browser (overrides --headless)",
    )

    # ==========================================================================
    # Agent configuration
    # ==========================================================================
    agent_group = p.add_argument_group("Agent Options")
    agent_group.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum steps before giving up (default: 30)",
    )
    agent_group.add_argument(
        "--max-replans",
        type=int,
        default=2,
        help="Maximum replans on failure (default: 2)",
    )
    agent_group.add_argument(
        "--stepwise",
        action="store_true",
        help="Use stepwise (ReAct-style) planning instead of upfront planning",
    )
    agent_group.add_argument(
        "--verbose",
        action="store_true",
        help="Print plan and executor prompts to stdout",
    )
    agent_group.add_argument(
        "--verbose-pruning",
        action="store_true",
        help="Print pruning details (raw count, pruned count, relaxation level)",
    )
    agent_group.add_argument(
        "--force-category",
        type=str,
        choices=["shopping", "form_filling", "search", "extraction", "navigation", "auth", "checkout", "verification", "generic"],
        default=None,
        help="Force a specific pruning category (overrides auto-detection)",
    )
    agent_group.add_argument(
        "--use-page-context",
        action="store_true",
        default=False,
        help="Extract page markdown for better planning (adds token cost)",
    )
    agent_group.add_argument(
        "--page-context-max-chars",
        type=int,
        default=8000,
        help="Max characters of page markdown to include (default: 8000)",
    )

    # ==========================================================================
    # Output options
    # ==========================================================================
    output_group = p.add_argument_group("Output Options")
    output_group.add_argument(
        "--out-dir",
        type=str,
        default="runs",
        help="Output directory for artifacts (default: runs)",
    )
    output_group.add_argument(
        "--json-output",
        action="store_true",
        help="Output result as JSON",
    )

    return p


def print_templates():
    """Print all available task templates."""
    templates = list_tasks()
    print("\n" + "=" * 60)
    print("Available Task Templates")
    print("=" * 60)

    for category, task_keys in sorted(templates.items()):
        print(f"\n{category.upper()}:")
        print("-" * 40)
        for key in sorted(task_keys):
            task = ALL_TASKS[key]
            print(f"  {key}")
            print(f"    URL: {task.starting_url}")
            print(f"    Task: {task.task[:60]}...")
            print()

    print("=" * 60)
    print("Usage: python main.py --template <template_name>")
    print("=" * 60 + "\n")


def get_task_definition(args: argparse.Namespace) -> TaskDefinition:
    """
    Get task definition from CLI arguments.

    Priority:
    1. --template (pre-defined task)
    2. --task + --url (custom task)
    3. Error if neither specified
    """
    if args.template:
        try:
            task = get_task(args.template)
            logger.info(f"Using template: {args.template}")
            return task
        except KeyError as e:
            logger.error(str(e))
            print_templates()
            sys.exit(1)

    if args.task:
        url = args.url or "https://www.google.com"
        category = TaskCategory(args.category)
        return create_custom_task(
            starting_url=url,
            task=args.task,
            category=category,
        )

    logger.error("Must specify either --task or --template")
    sys.exit(1)


def _map_demo_category_to_sdk(category: TaskCategory) -> SdkTaskCategory:
    """Map demo/WebBench categories to SDK automation categories."""
    mapping = {
        TaskCategory.READ: SdkTaskCategory.EXTRACTION,
        TaskCategory.CREATE: SdkTaskCategory.FORM_FILL,
        TaskCategory.UPDATE: SdkTaskCategory.FORM_FILL,
        TaskCategory.DELETE: SdkTaskCategory.TRANSACTION,
        TaskCategory.TRANSACTION: SdkTaskCategory.TRANSACTION,
    }
    return mapping[category]


def build_automation_task(
    task_def: TaskDefinition,
    *,
    max_steps: int,
    force_pruning_category: str | None = None,
) -> AutomationTask:
    """Build an SDK AutomationTask from the demo task definition."""
    task_with_context = (
        f"{task_def.task}\n\n"
        f"IMPORTANT: The browser is ALREADY at {task_def.starting_url}. "
        f"Do NOT include a NAVIGATE step to this URL. Start directly with the first action "
        f"(e.g., TYPE_AND_SUBMIT for search, CLICK for buttons)."
    )
    success_criteria = None
    if task_def.success_predicates:
        success_criteria = SuccessCriteria(
            predicates=task_def.success_predicates,
            require_all=True,
        )

    return AutomationTask(
        task_id=task_def.task_id,
        starting_url=task_def.starting_url,
        task=task_with_context,
        category=_map_demo_category_to_sdk(task_def.category),
        success_criteria=success_criteria,
        domain_hints=task_def.domain_hints,
        enable_recovery=task_def.enable_recovery,
        max_recovery_attempts=2,
        max_steps=max_steps,
        force_pruning_category=force_pruning_category,
    )


async def run_agent(
    task_def: TaskDefinition,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    Run the PlannerExecutorAgent with the given task and configuration.

    Args:
        task_def: Task definition
        args: CLI arguments

    Returns:
        Result dictionary
    """
    # Determine headless mode
    headless = args.headless and not args.no_headless

    # Get Predicate API key for cloud features
    predicate_api_key = os.getenv("PREDICATE_API_KEY")
    use_api = bool((predicate_api_key or "").strip())

    # Create LLM providers
    logger.info(f"Creating LLM providers (mode={args.provider})")
    planner, executor = create_planner_executor_providers(
        mode=args.provider,
        planner_model=args.planner_model,
        executor_model=args.executor_model,
        planner_provider=args.planner_provider,
        executor_provider=args.executor_provider,
    )

    # Create agent configuration
    config = PlannerExecutorConfig(
        # Snapshot escalation for reliable element capture
        snapshot=SnapshotEscalationConfig(
            enabled=True,
            limit_base=60,
            limit_step=30,
            limit_max=200,
        ),
        # Vision fallback for complex pages
        vision=VisionFallbackConfig(
            enabled=True,
            max_vision_calls=3,
            trigger_requires_vision=True,
            trigger_canvas_or_low_actionables=True,
        ),
        # Retry/verification settings
        retry=RetryConfig(
            verify_timeout_s=15.0,
            verify_poll_s=0.5,
            verify_max_attempts=6,
            executor_repair_attempts=3,
            max_replans=args.max_replans,
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
        # Verbose mode (includes pruning details if --verbose-pruning is set)
        verbose=args.verbose or getattr(args, 'verbose_pruning', False),
        # Page context for planning (extracts markdown from page for better plans)
        use_page_context=getattr(args, 'use_page_context', False),
        page_context_max_chars=getattr(args, 'page_context_max_chars', 8000),
    )

    # Create tracer
    tracer = create_tracer(
        goal=task_def.task,
        agent_type="PlannerExecutorAgent",
    )

    # Get heuristics for the domain
    heuristics = get_heuristics_for_domain(task_def.domain_hints)

    # Create agent
    agent = PlannerExecutorAgent(
        planner=planner,
        executor=executor,
        config=config,
        tracer=tracer,
        intent_heuristics=heuristics,
    )

    logger.info("=" * 60)
    logger.info("Starting Browser Automation")
    logger.info("=" * 60)
    logger.info(f"Task ID: {task_def.task_id}")
    logger.info(f"Task: {task_def.task}")
    logger.info(f"Starting URL: {task_def.starting_url}")
    logger.info(f"Category: {task_def.category.value}")
    logger.info(f"Headless: {headless}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Predicate API: {'enabled' if use_api else 'disabled'}")
    logger.info(f"Page context: {'enabled' if getattr(args, 'use_page_context', False) else 'disabled'}")
    logger.info("=" * 60)

    # Permission policy for common browser prompts
    permission_policy = {
        "auto_grant": [
            "geolocation",
            "notifications",
            "clipboard-read",
            "clipboard-write",
        ],
        "geolocation": {"latitude": 47.6762, "longitude": -122.2057},
    }

    # Run automation
    async with AsyncPredicateBrowser(
        api_key=predicate_api_key,
        headless=headless,
        permission_policy=permission_policy,
    ) as browser:
        page = browser.page

        # Navigate to starting URL
        await page.goto(task_def.starting_url)
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        # Create runtime
        backend = PlaywrightBackend(page)
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            predicate_api_key=predicate_api_key,
            snapshot_options=SnapshotOptions(
                limit=60,
                screenshot=True,
                show_overlay=True,
                goal=task_def.task,
                use_api=True if use_api else None,
                predicate_api_key=predicate_api_key if use_api else None,
            ),
        )

        try:
            # Dismiss initial overlays (cookie banners, popups) before agent runs
            logger.info("Dismissing initial overlays...")
            try:
                overlay_result = await dismiss_overlays_before_agent(
                    runtime,
                    browser,
                    use_api=True if use_api else None,
                    verbose=args.verbose,
                )
                logger.info(
                    f"Overlay dismissal: {overlay_result.status} "
                    f"(before={overlay_result.overlays_before}, after={overlay_result.overlays_after})"
                )
                if overlay_result.actions:
                    logger.info(f"  Actions: {', '.join(overlay_result.actions)}")
            except Exception as e:
                logger.warning(f"Overlay dismissal failed: {e}")
                import traceback
                traceback.print_exc()

            automation_task = build_automation_task(
                task_def,
                max_steps=args.max_steps,
                force_pruning_category=getattr(args, 'force_category', None),
            )

            # Run the agent
            if args.stepwise:
                result = await agent.run_stepwise(runtime, automation_task)
            else:
                result = await agent.run(runtime, automation_task)

            # Get token usage
            token_stats = agent.get_token_stats()

            logger.info("=" * 60)
            logger.info("Run Complete")
            logger.info("=" * 60)
            logger.info(f"Success: {result.success}")
            logger.info(f"Steps completed: {result.steps_completed}/{result.steps_total}")
            logger.info(f"Replans used: {result.replans_used}")
            logger.info(f"Duration: {result.total_duration_ms}ms")
            logger.info(f"Total tokens: {token_stats['total']['total_tokens']}")
            compact_token_summary = format_compact_token_summary(token_stats)
            if compact_token_summary:
                logger.info(f"Token summary: {compact_token_summary}")

            if result.error:
                logger.error(f"Error: {result.error}")

            # Log step outcomes
            for outcome in result.step_outcomes:
                status = "OK" if outcome.verification_passed else "FAIL"
                vision = " [vision]" if outcome.used_vision else ""
                logger.info(
                    f"  Step {outcome.step_id}: {outcome.goal[:50]}... - {status}{vision}"
                )
                if outcome.extracted_data is not None:
                    logger.info(f"    Extracted: {json.dumps(outcome.extracted_data, ensure_ascii=False)[:500]}")

            return {
                "success": result.success,
                "task_id": task_def.task_id,
                "task": task_def.task,
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "replans_used": result.replans_used,
                "duration_ms": result.total_duration_ms,
                "error": result.error,
                "token_usage": token_stats,
                "token_summary": compact_token_summary,
                "final_url": result.step_outcomes[-1].url_after if result.step_outcomes else None,
                "extracted_data": [
                    outcome.extracted_data
                    for outcome in result.step_outcomes
                    if outcome.extracted_data is not None
                ],
            }

        except Exception as e:
            logger.exception(f"Agent failed: {e}")
            return {
                "success": False,
                "task_id": task_def.task_id,
                "task": task_def.task,
                "error": str(e),
            }
        finally:
            tracer.close()


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Handle --list-templates
    if args.list_templates:
        print_templates()
        sys.exit(0)

    # Check for required API keys
    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "OPENAI_API_KEY environment variable is required for OpenAI provider.\n"
            "Either set OPENAI_API_KEY or use a different provider:\n"
            "  --provider deepinfra (requires DEEPINFRA_API_KEY)\n"
            "  --provider ollama (requires Ollama running locally)\n"
            "  --provider mlx (Apple Silicon only)"
        )
        sys.exit(1)

    if args.provider == "deepinfra" and not os.getenv("DEEPINFRA_API_KEY"):
        logger.error(
            "DEEPINFRA_API_KEY environment variable is required for DeepInfra provider."
        )
        sys.exit(1)

    # Get task definition
    task_def = get_task_definition(args)

    # Run the agent
    result = asyncio.run(run_agent(task_def, args))

    # Output result
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Success: {result['success']}")
        print(f"Task: {result['task'][:60]}...")
        if result.get("steps_completed"):
            print(f"Steps: {result['steps_completed']}/{result['steps_total']}")
        if result.get("duration_ms"):
            print(f"Duration: {result['duration_ms']}ms")
        if result.get("token_summary"):
            print(f"Token summary: {result['token_summary']}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("final_url"):
            print(f"Final URL: {result['final_url'][:80]}...")
        print("=" * 60 + "\n")

    # Exit with appropriate code
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
