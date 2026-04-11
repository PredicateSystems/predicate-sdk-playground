"""
Generic Browser Agent Demo

A modular demonstration of the Predicate SDK's PlannerExecutorAgent
for browser automation across diverse task categories.

Modules:
- task_definitions: Task templates and factory functions
- providers: LLM provider factory (OpenAI, DeepInfra, Ollama, MLX)
- heuristics: Domain-specific element selection heuristics

Note: Overlay dismissal utilities are now in the SDK:
    from predicate.overlay_dismissal import dismiss_overlays_before_agent

Usage:
    python main.py --task "Search for laptop on Amazon" --url https://amazon.com
    python main.py --provider deepinfra --template lifeisgood_shopping
    python main.py --list-templates
"""

from .task_definitions import (
    TaskCategory,
    TaskDefinition,
    create_custom_task,
    get_task,
    list_tasks,
    ALL_TASKS,
)

from .providers import (
    ProviderType,
    ModelConfig,
    create_provider,
    create_planner_executor_providers,
)

from .heuristics import (
    IntentHeuristics,
    EcommerceHeuristics,
    SearchHeuristics,
    FormHeuristics,
    CombinedHeuristics,
    get_heuristics_for_domain,
)

# Re-export from SDK for backwards compatibility
from predicate.overlay_dismissal import (
    OverlayDismissResult,
    dismiss_overlays,
    dismiss_overlays_before_agent,
)

__all__ = [
    # Task definitions
    "TaskCategory",
    "TaskDefinition",
    "create_custom_task",
    "get_task",
    "list_tasks",
    "ALL_TASKS",
    # Providers
    "ProviderType",
    "ModelConfig",
    "create_provider",
    "create_planner_executor_providers",
    # Heuristics
    "IntentHeuristics",
    "EcommerceHeuristics",
    "SearchHeuristics",
    "FormHeuristics",
    "CombinedHeuristics",
    "get_heuristics_for_domain",
    # Overlay utilities (from SDK)
    "OverlayDismissResult",
    "dismiss_overlays",
    "dismiss_overlays_before_agent",
]
