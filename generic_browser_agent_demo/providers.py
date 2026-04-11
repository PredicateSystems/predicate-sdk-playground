"""
LLM Provider Factory for Generic Browser Agent Demo.

This module provides convenient factory functions for creating LLM providers
with pre-configured model defaults for different backends.

Most providers are imported from the SDK. This module adds:
- MLXProvider for Apple Silicon local text models (SDK only has MLXVLMProvider for vision)
- Pre-configured model presets for quick setup
- Factory function for creating planner/executor pairs

For basic usage, prefer the SDK's create_planner_executor_agent() function:
    from predicate.agents import create_planner_executor_agent
    agent = create_planner_executor_agent(
        planner_model="gpt-4o",
        executor_model="gpt-4o-mini",
    )
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Import providers from SDK
from predicate.llm_provider import LLMProvider, LLMResponse, OllamaProvider, OpenAIProvider

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    DEEPINFRA = "deepinfra"
    OLLAMA = "ollama"
    MLX = "mlx"


@dataclass
class ModelConfig:
    """Configuration for a model."""

    provider: ProviderType
    model_name: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048


# =============================================================================
# Pre-configured Model Defaults
# =============================================================================

# Cloud models (recommended for best quality)
CLOUD_MODELS = {
    "planner": ModelConfig(
        provider=ProviderType.OPENAI,
        model_name="gpt-4o",
    ),
    "executor": ModelConfig(
        provider=ProviderType.OPENAI,
        model_name="gpt-4o-mini",
        max_tokens=96,
    ),
}

# DeepInfra models (good quality, lower cost)
# Note: Use Mistral for executor - Qwen models enter "thinking mode" and output
# <think> tags instead of actions. Mistral provides direct action responses.
DEEPINFRA_MODELS = {
    "planner": ModelConfig(
        provider=ProviderType.DEEPINFRA,
        model_name="Qwen/Qwen2.5-72B-Instruct",
        base_url="https://api.deepinfra.com/v1/openai",
    ),
    "executor": ModelConfig(
        provider=ProviderType.DEEPINFRA,
        model_name="mistralai/Mistral-Small-24B-Instruct-2501",
        base_url="https://api.deepinfra.com/v1/openai",
        max_tokens=96,
    ),
}

# Local MLX models (Apple Silicon)
MLX_MODELS = {
    "planner": ModelConfig(
        provider=ProviderType.MLX,
        model_name="mlx-community/Qwen3-8B-4bit",
    ),
    "executor": ModelConfig(
        provider=ProviderType.MLX,
        model_name="mlx-community/Qwen3-4B-4bit",
        max_tokens=96,
    ),
}

# Local Ollama models
OLLAMA_MODELS = {
    "planner": ModelConfig(
        provider=ProviderType.OLLAMA,
        model_name="qwen2.5:14b",
        base_url="http://localhost:11434",
    ),
    "executor": ModelConfig(
        provider=ProviderType.OLLAMA,
        model_name="qwen2.5:7b",
        base_url="http://localhost:11434",
        max_tokens=96,
    ),
}


# =============================================================================
# MLX Provider (not in SDK - SDK only has MLXVLMProvider for vision)
# =============================================================================


class MLXProvider(LLMProvider):
    """
    MLX-based local LLM provider for Apple Silicon (text-only).

    This is for text generation models. For vision models, use SDK's MLXVLMProvider.

    Requires: pip install mlx-lm
    """

    def __init__(self, model: str, max_tokens: int = 2048, temperature: float = 0.0):
        super().__init__(model)
        self._model_name_str = model
        self._default_max_tokens = max_tokens
        self._default_temperature = temperature

        try:
            self._mlx_lm = importlib.import_module("mlx_lm")
        except ImportError as exc:
            raise RuntimeError(
                "mlx-lm is required for MLX models. Install with: pip install mlx-lm"
            ) from exc

        load_fn = getattr(self._mlx_lm, "load", None)
        if not load_fn:
            raise RuntimeError("mlx_lm.load not available")

        logger.info(f"Loading MLX model: {model}")
        self.model, self.tokenizer = load_fn(model)
        logger.info(f"MLX model loaded: {model}")

    def _build_prompt(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
            # Disable thinking mode for Qwen 3 models
            if "qwen3" in self._model_name_str.lower():
                kwargs["enable_thinking"] = False
            return apply_chat_template(messages, **kwargs)
        return f"{system}\n\n{user}"

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        prompt = self._build_prompt(system_prompt, user_prompt)

        generate_fn = getattr(self._mlx_lm, "generate", None)
        if not generate_fn:
            raise RuntimeError("mlx_lm.generate not available")

        max_tokens = kwargs.get("max_tokens", self._default_max_tokens)
        temperature = kwargs.get("temperature", self._default_temperature)

        gen_kwargs: dict[str, Any] = {"max_tokens": max_tokens}
        if temperature and temperature > 0:
            try:
                sample_utils = importlib.import_module("mlx_lm.sample_utils")
                make_sampler = getattr(sample_utils, "make_sampler", None)
                if callable(make_sampler):
                    gen_kwargs["sampler"] = make_sampler(temp=temperature)
            except Exception:
                pass

        text = generate_fn(self.model, self.tokenizer, prompt, **gen_kwargs)

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
        return False

    @property
    def model_name(self) -> str:
        return self._model_name_str

    def supports_vision(self) -> bool:
        return False


# =============================================================================
# Provider Factory Functions
# =============================================================================


def create_provider(config: ModelConfig) -> LLMProvider:
    """
    Create an LLM provider from configuration.

    Args:
        config: ModelConfig specifying provider type and settings

    Returns:
        LLMProvider instance
    """
    if config.provider == ProviderType.OPENAI:
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return OpenAIProvider(model=config.model_name, api_key=api_key)

    elif config.provider == ProviderType.DEEPINFRA:
        api_key = config.api_key or os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            raise ValueError("DEEPINFRA_API_KEY environment variable is required")
        return OpenAIProvider(
            model=config.model_name,
            api_key=api_key,
            base_url=config.base_url or "https://api.deepinfra.com/v1/openai",
        )

    elif config.provider == ProviderType.OLLAMA:
        return OllamaProvider(
            model=config.model_name,
            base_url=config.base_url or "http://localhost:11434",
        )

    elif config.provider == ProviderType.MLX:
        return MLXProvider(
            model=config.model_name,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    else:
        raise ValueError(f"Unknown provider type: {config.provider}")


def _get_base_configs(mode: str) -> dict[str, ModelConfig]:
    """Get base configs for a provider mode."""
    if mode == "cloud" or mode == "openai":
        return CLOUD_MODELS
    elif mode == "deepinfra":
        return DEEPINFRA_MODELS
    elif mode == "ollama":
        return OLLAMA_MODELS
    elif mode == "mlx":
        return MLX_MODELS
    else:
        raise ValueError(f"Unknown mode: {mode}. Use: cloud, deepinfra, ollama, mlx")


def _get_provider_config(provider_name: str, role: str) -> ModelConfig:
    """Get default config for a specific provider/role pair."""
    configs_by_provider = {
        "openai": CLOUD_MODELS,
        "deepinfra": DEEPINFRA_MODELS,
        "ollama": OLLAMA_MODELS,
        "mlx": MLX_MODELS,
    }
    if provider_name not in configs_by_provider:
        raise ValueError(f"Unknown provider: {provider_name}")
    base = configs_by_provider[provider_name][role]
    return ModelConfig(
        provider=base.provider,
        model_name=base.model_name,
        api_key=base.api_key,
        base_url=base.base_url,
        temperature=base.temperature,
        max_tokens=base.max_tokens,
    )


def create_planner_executor_providers(
    mode: str = "cloud",
    planner_model: str | None = None,
    executor_model: str | None = None,
    planner_provider: str | None = None,
    executor_provider: str | None = None,
) -> tuple[LLMProvider, LLMProvider]:
    """
    Create planner and executor providers based on mode.

    Args:
        mode: "cloud" (OpenAI), "deepinfra", "ollama", or "mlx"
        planner_model: Override planner model name
        executor_model: Override executor model name
        planner_provider: Override planner provider (e.g., "openai", "deepinfra")
        executor_provider: Override executor provider

    Returns:
        Tuple of (planner_provider, executor_provider)

    Example:
        # Use deepinfra for both
        planner, executor = create_planner_executor_providers(mode="deepinfra")

        # Mix providers: OpenAI planner, DeepInfra executor
        planner, executor = create_planner_executor_providers(
            mode="cloud",
            executor_provider="deepinfra",
        )
    """
    # Get base configs for mode
    base_configs = _get_base_configs(mode)

    # Start with base configs, then apply provider overrides
    if planner_provider:
        planner_config = _get_provider_config(planner_provider, "planner")
    else:
        planner_config = ModelConfig(
            provider=base_configs["planner"].provider,
            model_name=base_configs["planner"].model_name,
            api_key=base_configs["planner"].api_key,
            base_url=base_configs["planner"].base_url,
            temperature=base_configs["planner"].temperature,
            max_tokens=base_configs["planner"].max_tokens,
        )

    if executor_provider:
        executor_config = _get_provider_config(executor_provider, "executor")
    else:
        executor_config = ModelConfig(
            provider=base_configs["executor"].provider,
            model_name=base_configs["executor"].model_name,
            api_key=base_configs["executor"].api_key,
            base_url=base_configs["executor"].base_url,
            temperature=base_configs["executor"].temperature,
            max_tokens=base_configs["executor"].max_tokens,
        )

    # Apply model name overrides
    if planner_model:
        planner_config = ModelConfig(
            provider=planner_config.provider,
            model_name=planner_model,
            api_key=planner_config.api_key,
            base_url=planner_config.base_url,
            temperature=planner_config.temperature,
            max_tokens=planner_config.max_tokens,
        )

    if executor_model:
        executor_config = ModelConfig(
            provider=executor_config.provider,
            model_name=executor_model,
            api_key=executor_config.api_key,
            base_url=executor_config.base_url,
            temperature=executor_config.temperature,
            max_tokens=executor_config.max_tokens,
        )

    logger.info(f"Creating providers (mode={mode})")
    logger.info(f"  Planner: {planner_config.provider.value} / {planner_config.model_name}")
    logger.info(f"  Executor: {executor_config.provider.value} / {executor_config.model_name}")

    planner = create_provider(planner_config)
    executor = create_provider(executor_config)

    return planner, executor
