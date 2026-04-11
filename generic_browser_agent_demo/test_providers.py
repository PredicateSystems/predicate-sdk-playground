from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from providers import create_planner_executor_providers


def test_create_planner_executor_providers_honors_provider_overrides() -> None:
    planner, executor = create_planner_executor_providers(
        mode="openai",
        planner_provider="ollama",
        executor_provider="ollama",
        planner_model="qwen2.5:14b",
        executor_model="qwen2.5:7b",
    )

    assert planner.__class__.__name__ == "OllamaProvider"
    assert executor.__class__.__name__ == "OllamaProvider"
    assert planner.model_name == "qwen2.5:14b"
    assert executor.model_name == "qwen2.5:7b"
