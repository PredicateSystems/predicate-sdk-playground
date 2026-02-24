# Local LLM Integration with Predicate SDK

*Design guide for integrating small, local LLMs (Qwen 2.5 3B, Gemma 2 2B/9B) with Predicate Python SDK*

---

## Overview

This document outlines a design for integrating **small, local language models** with the Predicate SDK as an alternative to cloud-based LLMs like GPT-4. Local LLMs offer:

- **Zero API costs**: No per-token charges
- **Privacy**: All processing happens locally
- **Low latency**: No network round trips
- **Offline capability**: Works without internet

However, they come with constraints:
- **Limited context windows**: 2K-8K tokens (vs 128K for GPT-4)
- **Reduced reasoning**: Less sophisticated than frontier models
- **Quality variance**: More sensitive to prompt engineering

---

## Recommended Local Models

### Tier 1: Ultra-Light (1-3B parameters)
Best for: Real-time interactions, resource-constrained environments

| Model | Size | Context | Strengths |
|-------|------|---------|-----------|
| **Qwen 2.5 3B Instruct** | 3B | 32K | Best reasoning in class, instruction following |
| **Gemma 2 2B** | 2B | 8K | Fast inference, good balance |
| **Phi-3 Mini** | 3.8B | 4K | Microsoft-trained, strong on tasks |

### Tier 2: Light (7-9B parameters)
Best for: Better accuracy when resources allow

| Model | Size | Context | Strengths |
|-------|------|---------|-----------|
| **Qwen 2.5 7B Instruct** | 7B | 32K | Excellent reasoning, multilingual |
| **Gemma 2 9B** | 9B | 8K | Strong performance, Google-trained |
| **Llama 3.2 8B** | 8B | 128K | Meta's latest, huge context |

**Recommendation**: Start with **Qwen 2.5 3B Instruct** for best quality-to-size ratio.

---

## Architecture Design

### 1. Generic LLM Interface

Create an abstract interface that works for both cloud and local LLMs:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class LLMResponse:
    """Standardized LLM response"""
    content: str
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    tokens_used: Optional[int] = None

    def to_json(self) -> Dict[str, Any]:
        """Parse content as JSON"""
        import json
        return json.loads(self.content)


class BaseLLM(ABC):
    """Abstract base class for all LLM implementations"""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> LLMResponse:
        """Generate response from prompt"""
        pass

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """Check if model supports structured JSON output"""
        pass

    @property
    @abstractmethod
    def context_window(self) -> int:
        """Maximum context length in tokens"""
        pass

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether model runs locally"""
        pass
```

---

### 2. Local LLM Implementation

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import json


class LocalLLM(BaseLLM):
    """Local LLM implementation using Hugging Face transformers"""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        device: str = "auto",
        max_memory: Optional[Dict[int, str]] = None
    ):
        """
        Initialize local LLM

        Args:
            model_name: Hugging Face model identifier
            device: Device to run on ("cpu", "cuda", "mps", "auto")
            max_memory: Memory constraints per device
        """
        self.model_name = model_name
        self._context_window = self._infer_context_window(model_name)

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True
        )

        # Load model with optimal settings
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if device != "cpu" else torch.float32,
            device_map=device,
            max_memory=max_memory,
            trust_remote_code=True
        )
        self.model.eval()

        print(f"✅ Loaded {model_name} on {device}")

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_new_tokens: int = 512,
        temperature: float = 0.1,
        **kwargs
    ) -> LLMResponse:
        """Generate response using local model"""

        # Format prompt based on model type
        formatted_prompt = self._format_prompt(system_prompt, prompt)

        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self._context_window - max_new_tokens
        ).to(self.model.device)

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
                **kwargs
            )

        # Decode only the new tokens
        input_length = inputs['input_ids'].shape[1]
        generated_tokens = outputs[0][input_length:]
        response_text = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True
        ).strip()

        return LLMResponse(
            content=response_text,
            tokens_used=len(generated_tokens)
        )

    def _format_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Format prompt based on model's chat template"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        # Use model's native chat template if available
        if hasattr(self.tokenizer, 'apply_chat_template'):
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            # Fallback formatting
            formatted = ""
            if system_prompt:
                formatted += f"System: {system_prompt}\n\n"
            formatted += f"User: {user_prompt}\n\nAssistant:"
            return formatted

    def _infer_context_window(self, model_name: str) -> int:
        """Infer context window from model name"""
        context_map = {
            "qwen2.5": 32768,
            "qwen2": 32768,
            "gemma-2": 8192,
            "phi-3": 4096,
            "llama-3.2": 131072,
        }

        model_lower = model_name.lower()
        for key, value in context_map.items():
            if key in model_lower:
                return value

        return 2048  # Conservative default

    def supports_json_mode(self) -> bool:
        """Local models need prompt engineering for JSON"""
        return False  # Use prompt-based JSON extraction

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def is_local(self) -> bool:
        return True
```

---

### 3. Cloud LLM Implementation (for comparison)

```python
from openai import OpenAI


class CloudLLM(BaseLLM):
    """Cloud LLM implementation (OpenAI, Anthropic, etc.)"""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4-turbo-preview",
        api_key: Optional[str] = None
    ):
        self.provider = provider
        self.model = model

        if provider == "openai":
            self.client = OpenAI(api_key=api_key)
            self._context_window = 128000
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate using cloud API"""

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            **kwargs
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            tokens_used=response.usage.total_tokens
        )

    def supports_json_mode(self) -> bool:
        return True  # OpenAI supports response_format

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def is_local(self) -> bool:
        return False
```

---

## Element Processing Pipeline

### 1. Input: Raw Elements from Chrome Extension

The SDK receives raw DOM elements from the Chrome extension:

```python
@dataclass
class RawElement:
    """Raw element from Chrome extension"""
    id: int
    tag: str
    role: Optional[str]
    text: str
    bbox: Dict[str, float]  # {x, y, width, height}
    attributes: Dict[str, Any]

    # Visual cues
    is_visible: bool
    is_clickable: bool
    is_primary: bool
    in_viewport: bool

    # Computed properties
    importance_score: float
    background_color: Optional[str]
    text_color: Optional[str]


@dataclass
class ElementSnapshot:
    """Collection of elements from page"""
    url: str
    viewport: Dict[str, int]  # {width, height}
    elements: List[RawElement]
    timestamp: float
```

---

### 2. Element Filtering & Compression

**Critical for small LLMs**: Reduce element count before sending to model.

```python
class ElementFilter:
    """Filter and compress elements for small context windows"""

    @staticmethod
    def filter_by_task(
        elements: List[RawElement],
        task_type: str
    ) -> List[RawElement]:
        """
        Task-specific filtering to reduce noise

        Args:
            elements: All page elements
            task_type: One of ["find_input", "find_button", "find_link", "select_from_list"]

        Returns:
            Filtered elements relevant to task
        """
        filters = {
            "find_input": lambda e: e.role in ["textbox", "searchbox", "combobox", "input"],
            "find_button": lambda e: e.role == "button" and e.is_clickable,
            "find_link": lambda e: e.role == "link" and e.is_visible,
            "select_from_list": lambda e: e.role in ["link", "button", "option"] and e.in_viewport,
        }

        filter_fn = filters.get(task_type, lambda e: True)
        return [e for e in elements if filter_fn(e)]

    @staticmethod
    def top_k_by_importance(
        elements: List[RawElement],
        k: int = 20
    ) -> List[RawElement]:
        """Keep only top-k most important elements"""
        return sorted(
            elements,
            key=lambda e: e.importance_score,
            reverse=True
        )[:k]

    @staticmethod
    def compress_element(element: RawElement) -> Dict[str, Any]:
        """
        Compress element to minimal representation

        Reduces token usage by 60-70% while keeping essential info
        """
        return {
            "id": element.id,
            "role": element.role or element.tag,
            "text": element.text[:100],  # Truncate long text
            "bbox": {
                "x": int(element.bbox["x"]),
                "y": int(element.bbox["y"]),
                "w": int(element.bbox["width"]),
                "h": int(element.bbox["height"])
            },
            "clickable": element.is_clickable,
            "visible": element.is_visible,
            "score": round(element.importance_score, 2)
        }

    @staticmethod
    def prepare_for_llm(
        snapshot: ElementSnapshot,
        task_type: str,
        max_elements: int = 15
    ) -> Dict[str, Any]:
        """
        Complete pipeline: filter -> rank -> compress

        Args:
            snapshot: Full page snapshot
            task_type: Type of task to optimize for
            max_elements: Maximum elements to include

        Returns:
            Compressed representation for LLM
        """
        # Filter by task
        filtered = ElementFilter.filter_by_task(
            snapshot.elements,
            task_type
        )

        # Take top-k by importance
        top_elements = ElementFilter.top_k_by_importance(
            filtered,
            k=max_elements
        )

        # Compress each element
        compressed = [
            ElementFilter.compress_element(e)
            for e in top_elements
        ]

        return {
            "url": snapshot.url,
            "viewport": snapshot.viewport,
            "elements": compressed,
            "count": len(compressed)
        }
```

---

### 3. Prompt Engineering for Small LLMs

**Key principles**:
- Ultra-concise instructions
- Explicit output format
- Numbered steps
- Examples included

```python
class PromptBuilder:
    """Build optimized prompts for small LLMs"""

    SYSTEM_PROMPTS = {
        "default": "You are a web automation assistant. Respond ONLY with valid JSON.",
        "compact": "Web automation agent. Output JSON only."
    }

    @staticmethod
    def build_task_prompt(
        task_type: str,
        compressed_elements: Dict[str, Any],
        additional_context: str = ""
    ) -> str:
        """
        Build task-specific prompt optimized for small LLMs

        Uses minimal tokens while being explicit
        """

        if task_type == "find_input":
            return PromptBuilder._build_find_input_prompt(
                compressed_elements,
                additional_context
            )
        elif task_type == "find_button":
            return PromptBuilder._build_find_button_prompt(
                compressed_elements,
                additional_context
            )
        elif task_type == "find_link":
            return PromptBuilder._build_find_link_prompt(
                compressed_elements,
                additional_context
            )
        elif task_type == "select_from_list":
            return PromptBuilder._build_select_from_list_prompt(
                compressed_elements,
                additional_context
            )
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    @staticmethod
    def _build_find_input_prompt(
        elements: Dict[str, Any],
        context: str
    ) -> str:
        """Find input field (search box, text input, etc.)"""

        return f"""Task: Find the {context or 'input field'} to click on.

Elements (id, role, text, bbox, score):
{PromptBuilder._format_elements_compact(elements['elements'])}

Instructions:
1. Find element with role="textbox" or "searchbox"
2. Prefer higher score
3. Must be visible and clickable

Output JSON:
{{
  "id": <element_id>,
  "reasoning": "<brief reason>"
}}"""

    @staticmethod
    def _build_find_button_prompt(
        elements: Dict[str, Any],
        context: str
    ) -> str:
        """Find button to click"""

        return f"""Task: Find the "{context}" button.

Elements (id, role, text, bbox, score):
{PromptBuilder._format_elements_compact(elements['elements'])}

Instructions:
1. Find button with text matching "{context}" (case-insensitive)
2. Must be clickable
3. Prefer higher score

Output JSON:
{{
  "id": <element_id>,
  "reasoning": "<brief reason>"
}}"""

    @staticmethod
    def _build_find_link_prompt(
        elements: Dict[str, Any],
        context: str
    ) -> str:
        """Find link to click"""

        return f"""Task: Select a link from search results. {context}

Elements (id, role, text, bbox, score):
{PromptBuilder._format_elements_compact(elements['elements'])}

Instructions:
1. Find role="link"
2. Avoid text with "Ad" or "Sponsored"
3. Prefer top-left position (lower y-coordinate)
4. Must be visible

Output JSON:
{{
  "id": <element_id>,
  "reasoning": "<brief reason>"
}}"""

    @staticmethod
    def _build_select_from_list_prompt(
        elements: Dict[str, Any],
        context: str
    ) -> str:
        """Select item from a list"""

        return f"""Task: Select {context} from the list.

Elements (id, role, text, bbox, score):
{PromptBuilder._format_elements_compact(elements['elements'])}

Instructions:
1. Match text to "{context}" (partial match OK)
2. Prefer exact match over partial
3. Must be clickable
4. Prefer higher score

Output JSON:
{{
  "id": <element_id>,
  "match_quality": "<exact|partial>",
  "reasoning": "<brief reason>"
}}"""

    @staticmethod
    def _format_elements_compact(elements: List[Dict]) -> str:
        """Format elements in ultra-compact representation"""
        lines = []
        for e in elements:
            bbox_str = f"({e['bbox']['x']},{e['bbox']['y']},{e['bbox']['w']}x{e['bbox']['h']})"
            text_preview = e['text'][:50].replace('\n', ' ')
            lines.append(
                f"[{e['id']}] {e['role']:12} '{text_preview}' {bbox_str} score={e['score']}"
            )
        return '\n'.join(lines)
```

---

### 4. Response Parser

Handle both JSON and text responses from small LLMs:

```python
import json
import re
from typing import Optional


class ResponseParser:
    """Parse and validate LLM responses"""

    @staticmethod
    def extract_json(response: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from response, handling common issues

        Small LLMs sometimes add markdown or explanation
        """
        # Try direct parse first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        match = re.search(json_pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def validate_element_selection(
        parsed: Dict[str, Any],
        available_ids: List[int]
    ) -> bool:
        """Validate that selected element ID exists"""
        if "id" not in parsed:
            return False

        selected_id = parsed["id"]
        return selected_id in available_ids

    @staticmethod
    def safe_parse(
        response: LLMResponse,
        available_ids: List[int]
    ) -> Optional[Dict[str, Any]]:
        """
        Safely parse response with validation

        Returns None if parsing or validation fails
        """
        # Extract JSON
        parsed = ResponseParser.extract_json(response.content)
        if parsed is None:
            print("⚠️ Failed to extract JSON from response")
            return None

        # Validate
        if not ResponseParser.validate_element_selection(parsed, available_ids):
            print(f"⚠️ Invalid element ID: {parsed.get('id')}")
            return None

        return parsed
```

---

## Complete Integration Example

### Putting It All Together

```python
from typing import Optional, Dict, Any
from predicate import PredicateBrowser, snapshot, click_rect


class LocalLLMWebAgent:
    """Web automation agent using local LLM"""

    def __init__(
        self,
        llm: BaseLLM,
        max_elements: int = 15,
        verbose: bool = True
    ):
        """
        Initialize agent

        Args:
            llm: Local or cloud LLM instance
            max_elements: Max elements to send to LLM
            verbose: Print debug info
        """
        self.llm = llm
        self.max_elements = max_elements
        self.verbose = verbose

        self.element_filter = ElementFilter()
        self.prompt_builder = PromptBuilder()
        self.response_parser = ResponseParser()

    def find_and_click_element(
        self,
        browser: PredicateBrowser,
        task_type: str,
        context: str = ""
    ) -> bool:
        """
        Find and click an element using local LLM

        Args:
            browser: Sentience browser instance
            task_type: Type of element to find
            context: Additional context (button text, link description, etc.)

        Returns:
            True if successful, False otherwise
        """
        # Step 1: Get page snapshot
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"Task: {task_type} - {context}")
            print(f"{'='*70}")

        snapshot_data = snapshot(browser, screenshot=False)

        # Convert to structured format
        elements = [
            RawElement(
                id=elem.get('id', i),
                tag=elem.get('tag', ''),
                role=elem.get('role'),
                text=elem.get('text', ''),
                bbox=elem.get('bbox', {}),
                attributes=elem.get('attributes', {}),
                is_visible=elem.get('in_viewport', False),
                is_clickable=elem.get('visual_cues', {}).get('is_clickable', False),
                is_primary=elem.get('visual_cues', {}).get('is_primary', False),
                in_viewport=elem.get('in_viewport', False),
                importance_score=elem.get('importance_score', 0.0),
                background_color=elem.get('visual_cues', {}).get('background_color'),
                text_color=elem.get('visual_cues', {}).get('text_color')
            )
            for i, elem in enumerate(snapshot_data.get('elements', []))
        ]

        element_snapshot = ElementSnapshot(
            url=snapshot_data.get('url', ''),
            viewport=snapshot_data.get('viewport', {}),
            elements=elements,
            timestamp=snapshot_data.get('timestamp', 0.0)
        )

        # Step 2: Filter and compress elements
        compressed = self.element_filter.prepare_for_llm(
            element_snapshot,
            task_type=task_type,
            max_elements=self.max_elements
        )

        if self.verbose:
            print(f"Elements: {len(elements)} -> {compressed['count']} (after filtering)")

        if compressed['count'] == 0:
            print("❌ No relevant elements found after filtering")
            return False

        # Step 3: Build prompt
        user_prompt = self.prompt_builder.build_task_prompt(
            task_type=task_type,
            compressed_elements=compressed,
            additional_context=context
        )

        system_prompt = PromptBuilder.SYSTEM_PROMPTS["compact"]

        # Step 4: Generate response from LLM
        if self.verbose:
            print(f"Querying {self.llm.__class__.__name__}...")

        response = self.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_new_tokens=256,
            temperature=0.1
        )

        if self.verbose:
            print(f"Response ({response.tokens_used} tokens):")
            print(response.content)

        # Step 5: Parse response
        available_ids = [e['id'] for e in compressed['elements']]
        parsed = self.response_parser.safe_parse(response, available_ids)

        if parsed is None:
            print("❌ Failed to parse LLM response")
            return False

        # Step 6: Find the selected element and click
        selected_id = parsed['id']
        selected_element = next(
            (e for e in elements if e.id == selected_id),
            None
        )

        if selected_element is None:
            print(f"❌ Element {selected_id} not found in original snapshot")
            return False

        if self.verbose:
            print(f"✅ Selected element {selected_id}: {selected_element.text[:50]}")
            print(f"   Reasoning: {parsed.get('reasoning', 'N/A')}")

        # Click the element
        click_rect(browser, selected_element.bbox)

        return True


# Example usage
def demo_local_llm():
    """Demo: Google search with local LLM"""

    # Initialize local LLM
    llm = LocalLLM(
        model_name="Qwen/Qwen2.5-3B-Instruct",
        device="auto"
    )

    # Create agent
    agent = LocalLLMWebAgent(llm=llm, max_elements=15, verbose=True)

    # Run automation
    with PredicateBrowser(headless=False) as browser:
        # Navigate to Google
        browser.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        # Find and click search box
        success = agent.find_and_click_element(
            browser,
            task_type="find_input",
            context="search box"
        )

        if success:
            # Type query
            browser.page.keyboard.type("visiting japan")
            browser.page.keyboard.press("Enter")
            browser.page.wait_for_load_state("networkidle")

            # Select first non-ad result
            success = agent.find_and_click_element(
                browser,
                task_type="find_link",
                context="Select first organic (non-ad) search result"
            )

            if success:
                print("✅ Successfully clicked search result!")
            else:
                print("❌ Failed to find search result")
        else:
            print("❌ Failed to find search box")


if __name__ == "__main__":
    demo_local_llm()
```

---

## Performance Optimization

### 1. Model Quantization

Reduce memory and increase speed:

```python
from transformers import BitsAndBytesConfig

# 4-bit quantization (75% memory reduction)
quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4"
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-3B-Instruct",
    quantization_config=quantization_config,
    device_map="auto"
)
```

### 2. Batching (for multiple tasks)

```python
def batch_analyze_elements(
    llm: LocalLLM,
    tasks: List[Dict[str, Any]]
) -> List[Optional[Dict]]:
    """Process multiple tasks in one batch"""

    prompts = [
        PromptBuilder.build_task_prompt(
            task['type'],
            task['elements'],
            task['context']
        )
        for task in tasks
    ]

    # Batch tokenization
    inputs = llm.tokenizer(
        prompts,
        padding=True,
        return_tensors="pt"
    ).to(llm.model.device)

    # Batch generation
    with torch.no_grad():
        outputs = llm.model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1
        )

    # Decode all responses
    responses = llm.tokenizer.batch_decode(
        outputs,
        skip_special_tokens=True
    )

    return [
        ResponseParser.extract_json(resp)
        for resp in responses
    ]
```

### 3. Caching Common Patterns

```python
from functools import lru_cache

class CachedLocalLLM(LocalLLM):
    """Local LLM with response caching"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generate_cached = lru_cache(maxsize=100)(self._generate_impl)

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate with caching"""
        # Create cache key from prompt + kwargs
        cache_key = (prompt, frozenset(kwargs.items()))
        return self._generate_cached(cache_key)

    def _generate_impl(self, cache_key):
        """Actual generation (cached)"""
        prompt, kwargs_items = cache_key
        kwargs = dict(kwargs_items)
        return super().generate(prompt, **kwargs)
```

---

## Error Handling & Fallbacks

```python
class RobustLocalLLMAgent(LocalLLMWebAgent):
    """Agent with retry logic and fallbacks"""

    def find_and_click_element(
        self,
        browser: PredicateBrowser,
        task_type: str,
        context: str = "",
        max_retries: int = 2
    ) -> bool:
        """Find and click with retry logic"""

        for attempt in range(max_retries):
            try:
                success = super().find_and_click_element(
                    browser, task_type, context
                )

                if success:
                    return True

                if attempt < max_retries - 1:
                    print(f"⚠️ Attempt {attempt + 1} failed, retrying...")
                    # Increase max_elements for retry
                    self.max_elements = min(self.max_elements + 5, 30)

            except Exception as e:
                print(f"❌ Error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise

        return False
```

---

## Cost & Performance Comparison

### Local vs Cloud LLMs

| Aspect | Qwen 2.5 3B (Local) | GPT-4 Turbo (Cloud) |
|--------|---------------------|---------------------|
| **Cost per 1M tokens** | $0 (one-time download) | ~$15 |
| **Latency** | 200-500ms (local GPU) | 1000-3000ms (network) |
| **Context window** | 32K tokens | 128K tokens |
| **Accuracy** | 70-85% (with good prompts) | 95-99% |
| **Privacy** | 100% local | Data sent to OpenAI |
| **Hardware req** | 8GB+ VRAM (GPU) or 16GB RAM (CPU) | None |
| **Offline** | ✅ Yes | ❌ No |

### When to Use Local LLMs

**Best for**:
- High-volume automation (>1000 requests/day)
- Privacy-sensitive applications
- Offline/edge deployments
- Cost-sensitive projects
- Real-time interactive agents

**Not ideal for**:
- Complex reasoning tasks
- Long document analysis
- Mission-critical accuracy requirements
- Limited local compute resources

---

## Installation & Setup

### 1. Install Dependencies

```bash
# Core dependencies
pip install predicate-runtime
pip install transformers accelerate torch

# Optional: For quantization
pip install bitsandbytes

# Optional: For faster inference
pip install optimum
```

### 2. Download Model

```python
from transformers import AutoTokenizer, AutoModelForCausalLM

# Download Qwen 2.5 3B (one-time, ~6GB)
model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

print("✅ Model downloaded and cached locally")
```

### 3. Verify Setup

```python
# Test local LLM
llm = LocalLLM(model_name="Qwen/Qwen2.5-3B-Instruct")

response = llm.generate(
    prompt='Respond with JSON: {"status": "ok"}',
    system_prompt="You are a JSON assistant."
)

print(response.content)
# Expected: {"status": "ok"}
```

---

## Best Practices

### 1. Prompt Engineering
- Keep prompts under 1000 tokens for 3B models
- Use numbered instructions (1. 2. 3.)
- Include output format example
- Avoid complex reasoning chains

### 2. Element Filtering
- Always filter elements before sending to LLM
- Use task-specific filters (search vs button vs link)
- Limit to 10-20 elements max for 3B models
- Prioritize by importance score

### 3. Response Handling
- Implement robust JSON extraction
- Validate element IDs before clicking
- Use retry logic (2-3 attempts)
- Fall back to CSS selectors if LLM fails

### 4. Model Selection
- Start with Qwen 2.5 3B for best balance
- Use 7B+ models if accuracy is critical
- Use 2B models for ultra-fast responses
- Consider quantization for memory constraints

---

## Troubleshooting

### Issue: "CUDA out of memory"

**Solution**: Use quantization or CPU

```python
# Option 1: 4-bit quantization
llm = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    device="auto",
    load_in_4bit=True
)

# Option 2: Use CPU (slower but works)
llm = LocalLLM(
    model_name="Qwen/Qwen2.5-3B-Instruct",
    device="cpu"
)
```

### Issue: "LLM returns invalid JSON"

**Solution**: Improve prompt or use regex extraction

```python
# Add explicit JSON example to prompt
prompt = f"""Task: Find search box.

Elements: [...]

Output JSON (no markdown, no explanation):
{{
  "id": 42,
  "reasoning": "Element 42 is the search input"
}}

Your response:"""
```

### Issue: "Low accuracy on complex pages"

**Solution**: Increase max_elements or use larger model

```python
# More elements = better context
agent = LocalLLMWebAgent(
    llm=llm,
    max_elements=30  # Increased from 15
)

# Or use 7B model
llm = LocalLLM(model_name="Qwen/Qwen2.5-7B-Instruct")
```

---

## Future Enhancements

### 1. Fine-tuning on Web Automation Tasks
Train models specifically on web element selection:

```python
# Training data format
{
    "prompt": "Task: Find search box\n\nElements: [...]\n\nOutput JSON:",
    "completion": '{"id": 42, "reasoning": "..."}'
}
```

### 2. Multi-model Ensemble
Combine multiple local models for better accuracy:

```python
class EnsembleLLM:
    """Use multiple models and vote on best answer"""

    def __init__(self, models: List[LocalLLM]):
        self.models = models

    def generate(self, prompt: str, **kwargs):
        """Generate from all models and pick consensus"""
        responses = [
            model.generate(prompt, **kwargs)
            for model in self.models
        ]
        return self._vote(responses)
```

### 3. Hybrid Approach
Use local LLM for fast tasks, cloud for complex ones:

```python
class HybridLLM:
    """Smart routing between local and cloud"""

    def __init__(self, local: LocalLLM, cloud: CloudLLM):
        self.local = local
        self.cloud = cloud

    def generate(self, prompt: str, complexity: str = "simple", **kwargs):
        """Route based on task complexity"""
        if complexity == "simple":
            return self.local.generate(prompt, **kwargs)
        else:
            return self.cloud.generate(prompt, **kwargs)
```

---

## Conclusion

Local LLMs provide a **cost-effective, private, and fast** alternative to cloud-based models for web automation. Key takeaways:

1. **Qwen 2.5 3B** offers the best quality-to-size ratio
2. **Element filtering** is critical - reduce to 10-20 elements
3. **Prompt engineering** matters more for small models
4. **Expect 70-85% accuracy** vs 95%+ for GPT-4
5. **Use for high-volume, privacy-sensitive, or offline tasks**

For most web automation tasks, a well-optimized local 3B model can match 80% of GPT-4's performance at **zero marginal cost**.

---

## References

- [Qwen 2.5 Model Card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
- [Gemma 2 Documentation](https://huggingface.co/google/gemma-2-2b)
- [Hugging Face Transformers Docs](https://huggingface.co/docs/transformers)
- [Predicate Python SDK](https://github.com/PredicateLabs/sdk-python)

---

*Last updated: December 23, 2024*
