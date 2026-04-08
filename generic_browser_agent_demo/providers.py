"""
LLM Provider Factory for Generic Browser Agent Demo.

This module provides a unified interface for creating LLM providers,
supporting multiple backends:
- OpenAI API (GPT-4o, GPT-4o-mini)
- DeepInfra (Qwen, Llama, Mistral)
- Ollama (local models)
- MLX (Apple Silicon local models)
- HuggingFace Transformers (local models)

The PlannerExecutorAgent works with any LLMProvider implementation,
making it easy to swap between cloud and local models.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    DEEPINFRA = "deepinfra"
    OLLAMA = "ollama"
    MLX = "mlx"
    HUGGINGFACE = "huggingface"


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
# Default Model Configurations
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
# <think> tags instead of actions, even when instructed not to. Mistral provides
# direct action responses without reasoning. This matches webbench configuration.
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


def _get_sdk_path():
    """Get the SDK path for imports."""
    from pathlib import Path
    return Path(__file__).parent.parent.parent / "sdk-python"


def _ensure_sdk_imports():
    """Ensure SDK is importable."""
    import sys
    sdk_path = _get_sdk_path()
    if str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))


# =============================================================================
# Provider Implementations
# =============================================================================


def create_openai_provider(config: ModelConfig):
    """Create an OpenAI provider."""
    _ensure_sdk_imports()
    from predicate.llm_provider import OpenAIProvider

    api_key = config.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    return OpenAIProvider(
        model=config.model_name,
        api_key=api_key,
    )


def create_deepinfra_provider(config: ModelConfig):
    """Create a DeepInfra provider (OpenAI-compatible)."""
    _ensure_sdk_imports()
    from predicate.llm_provider import OpenAIProvider

    api_key = config.api_key or os.getenv("DEEPINFRA_API_KEY")
    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY environment variable is required")

    return OpenAIProvider(
        model=config.model_name,
        api_key=api_key,
        base_url=config.base_url or "https://api.deepinfra.com/v1/openai",
    )


def create_ollama_provider(config: ModelConfig):
    """Create an Ollama provider for local models."""
    _ensure_sdk_imports()
    from predicate.llm_provider import OllamaProvider

    return OllamaProvider(
        model=config.model_name,
        base_url=config.base_url or "http://localhost:11434",
    )


def create_mlx_provider(config: ModelConfig):
    """
    Create an MLX provider for Apple Silicon local models.

    Requires: pip install mlx-lm
    """
    _ensure_sdk_imports()
    from predicate.llm_provider import LLMProvider, LLMResponse

    class MLXProvider(LLMProvider):
        """MLX-based local LLM provider for Apple Silicon."""

        def __init__(self, model: str):
            super().__init__(model)
            self._model_name_str = model

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

            max_tokens = kwargs.get("max_tokens", config.max_tokens)
            temperature = kwargs.get("temperature", config.temperature)

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

    return MLXProvider(config.model_name)


def create_huggingface_provider(config: ModelConfig):
    """
    Create a HuggingFace Transformers provider.

    Requires: pip install torch transformers
    """
    _ensure_sdk_imports()
    from predicate.llm_provider import LLMProvider, LLMResponse

    class HuggingFaceProvider(LLMProvider):
        """HuggingFace Transformers-based local LLM provider."""

        def __init__(self, model: str):
            super().__init__(model)
            self._model_name_str = model

            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as exc:
                raise RuntimeError(
                    "torch and transformers are required. Install with: pip install torch transformers"
                ) from exc

            self._torch = torch

            # Determine device
            if torch.backends.mps.is_available():
                device_map = "mps"
                torch_dtype = torch.bfloat16
            elif torch.cuda.is_available():
                device_map = "auto"
                torch_dtype = torch.float16
            else:
                device_map = "cpu"
                torch_dtype = torch.float32

            logger.info(f"Loading HuggingFace model: {model} (device={device_map})")
            self.tokenizer = AutoTokenizer.from_pretrained(model, use_fast=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                model,
                device_map=device_map,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True,
            )
            logger.info(f"HuggingFace model loaded: {model}")

        def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            encoding = self.tokenizer.apply_chat_template(
                messages, return_tensors="pt", add_generation_prompt=True
            )

            device = getattr(self.model, "device", "cpu")
            try:
                input_ids = encoding["input_ids"].to(device)
                attention_mask = encoding.get("attention_mask")
                if attention_mask is not None:
                    attention_mask = attention_mask.to(device)
            except (TypeError, KeyError):
                input_ids = encoding.to(device)
                attention_mask = self._torch.ones_like(input_ids)

            max_tokens = kwargs.get("max_tokens", config.max_tokens)
            temperature = kwargs.get("temperature", config.temperature)
            do_sample = temperature > 0

            output_ids = self.model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_tokens,
                do_sample=do_sample,
                temperature=temperature if do_sample else None,
                pad_token_id=self.tokenizer.eos_token_id,
            )

            generated = output_ids[0][input_ids.shape[-1]:]
            text = self.tokenizer.decode(generated, skip_special_tokens=True)

            return LLMResponse(
                content=text.strip(),
                prompt_tokens=int(input_ids.shape[-1]),
                completion_tokens=int(generated.shape[-1]),
                total_tokens=int(input_ids.shape[-1]) + int(generated.shape[-1]),
                model_name=self._model_name_str,
            )

        def supports_json_mode(self) -> bool:
            return False

        @property
        def model_name(self) -> str:
            return self._model_name_str

        def supports_vision(self) -> bool:
            return False

    return HuggingFaceProvider(config.model_name)


# =============================================================================
# Factory Function
# =============================================================================

PROVIDER_FACTORIES = {
    ProviderType.OPENAI: create_openai_provider,
    ProviderType.DEEPINFRA: create_deepinfra_provider,
    ProviderType.OLLAMA: create_ollama_provider,
    ProviderType.MLX: create_mlx_provider,
    ProviderType.HUGGINGFACE: create_huggingface_provider,
}


def create_provider(config: ModelConfig):
    """
    Create an LLM provider from configuration.

    Args:
        config: ModelConfig specifying provider type and settings

    Returns:
        LLMProvider instance

    Example:
        provider = create_provider(ModelConfig(
            provider=ProviderType.OPENAI,
            model_name="gpt-4o",
        ))
    """
    factory = PROVIDER_FACTORIES.get(config.provider)
    if not factory:
        raise ValueError(f"Unknown provider type: {config.provider}")
    return factory(config)


def create_planner_executor_providers(
    mode: str = "cloud",
    planner_model: str | None = None,
    executor_model: str | None = None,
):
    """
    Create planner and executor providers based on mode.

    Args:
        mode: "cloud" (OpenAI), "deepinfra", "ollama", "mlx", or "huggingface"
        planner_model: Override planner model name
        executor_model: Override executor model name

    Returns:
        Tuple of (planner_provider, executor_provider)

    Example:
        planner, executor = create_planner_executor_providers(mode="deepinfra")
    """
    # Select base configs
    if mode == "cloud" or mode == "openai":
        base_configs = CLOUD_MODELS
    elif mode == "deepinfra":
        base_configs = DEEPINFRA_MODELS
    elif mode == "ollama":
        base_configs = OLLAMA_MODELS
    elif mode == "mlx":
        base_configs = MLX_MODELS
    elif mode == "huggingface" or mode == "hf":
        base_configs = {
            "planner": ModelConfig(
                provider=ProviderType.HUGGINGFACE,
                model_name="Qwen/Qwen2.5-7B-Instruct",
            ),
            "executor": ModelConfig(
                provider=ProviderType.HUGGINGFACE,
                model_name="Qwen/Qwen2.5-3B-Instruct",
                max_tokens=96,
            ),
        }
    else:
        raise ValueError(f"Unknown mode: {mode}. Use: cloud, deepinfra, ollama, mlx, huggingface")

    # Apply overrides
    planner_config = base_configs["planner"]
    executor_config = base_configs["executor"]

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
