from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from predicate.agents.automation_task import TaskCategory as SdkTaskCategory

from main import build_automation_task, format_compact_token_summary
from task_definitions import TaskCategory, TaskDefinition


def test_build_automation_task_maps_category_hints_and_success_criteria() -> None:
    task_def = TaskDefinition(
        task_id="demo-1",
        starting_url="https://shop.example.com",
        task="Add the product to cart and proceed to checkout.",
        category=TaskCategory.TRANSACTION,
        success_predicates=[{"predicate": "url_contains", "args": ["checkout"]}],
        domain_hints=("ecommerce", "shop"),
    )

    task = build_automation_task(task_def, max_steps=12)

    assert task.category == SdkTaskCategory.TRANSACTION
    assert task.domain_hints == ("ecommerce", "shop")
    assert task.max_steps == 12
    assert task.success_criteria is not None
    assert task.success_criteria.predicates == [{"predicate": "url_contains", "args": ["checkout"]}]
    assert "ALREADY at https://shop.example.com" in task.task


def test_build_automation_task_maps_read_to_extraction() -> None:
    task_def = TaskDefinition(
        task_id="demo-2",
        starting_url="https://example.com",
        task="Extract the product prices.",
        category=TaskCategory.READ,
    )

    task = build_automation_task(task_def, max_steps=5)

    assert task.category == SdkTaskCategory.EXTRACTION


def test_format_compact_token_summary_orders_roles_and_skips_empty() -> None:
    token_stats = {
        "total": {"total_tokens": 719},
        "by_role": {
            "extract": {"total_tokens": 200},
            "planner": {"total_tokens": 519},
            "executor": {"total_tokens": 0},
        },
    }

    assert format_compact_token_summary(token_stats) == "planner=519, extract=200"
