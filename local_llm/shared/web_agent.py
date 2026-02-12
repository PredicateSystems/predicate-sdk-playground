"""
Web automation agent using local or cloud LLMs
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from typing import Optional, Dict, Any
from models.base_llm import BaseLLM
from shared.element_processor import ElementSnapshot, ElementFilter
from shared.prompt_builder import PromptBuilder
from shared.response_parser import ResponseParser


class WebAgent:
    """Web automation agent using LLM for element selection"""

    def __init__(
        self,
        llm: BaseLLM,
        max_elements: int = 15,
        verbose: bool = True
    ):
        """
        Initialize web agent

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

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"Initialized WebAgent")
            print(f"  LLM: {self.llm}")
            print(f"  Max elements: {self.max_elements}")
            print(f"{'='*70}\n")

    def analyze_and_select(
        self,
        snapshot_data: Dict[str, Any],
        task_type: str,
        context: str = "",
        exclude_text_patterns: Optional[list] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze snapshot and select element using LLM

        Args:
            snapshot_data: Snapshot data from Predicate SDK
            task_type: Type of element to find ("find_input", "find_button", "find_link", "select_from_list")
            context: Additional context (button text, link description, etc.)
            exclude_text_patterns: Text patterns to exclude (e.g., ["Ad", "Sponsored"])

        Returns:
            Selected element data with ID and reasoning, or None if failed
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"Task: {task_type}")
            if context:
                print(f"Context: {context}")
            print(f"{'='*70}")

        # Step 1: Convert to structured format
        element_snapshot = ElementSnapshot.from_snapshot_data(snapshot_data)

        # Step 2: Apply smart filtering based on task type
        print(f"\n📊 Applying smart filtering for task: {task_type}")
        print(f"   Total elements in snapshot: {len(element_snapshot.elements)}")

        compressed = ElementFilter.prepare_for_llm(
            snapshot=element_snapshot,
            task_type=task_type,
            max_elements=self.max_elements,
            exclude_text_patterns=exclude_text_patterns
        )

        # Print all elements being sent to LLM
        print(f"\n📋 Elements being sent to LLM ({compressed['count']} elements):")
        print("=" * 100)
        for i, elem in enumerate(compressed['elements'], 1):
            text_preview = elem['text'][:50] if elem['text'] else "(no text)"
            bbox = elem['bbox']
            print(f"{i:2d}. [ID:{elem['id']:3d}] {elem['role']:15s} | '{text_preview}' | ({bbox['x']},{bbox['y']},{bbox['w']}x{bbox['h']}) | score={elem['score']:.2f}")
        print("=" * 100)

        if compressed['count'] == 0:
            print("❌ No elements found in snapshot")
            return None

        # Step 3: Build prompt
        user_prompt = self.prompt_builder.build_task_prompt(
            task_type=task_type,
            compressed_elements=compressed,
            additional_context=context
        )

        system_prompt = PromptBuilder.get_system_prompt("compact")

        if self.verbose:
            print(f"\n🤖 Querying LLM...")
            print(f"   Model: {self.llm.model_name}")
            print(f"   Elements sent: {compressed['count']}")
            print(f"\n💬 SYSTEM PROMPT:")
            print(f"   {system_prompt}")
            print(f"\n💬 USER PROMPT:")
            print("-" * 100)
            print(user_prompt)
            print("-" * 100)

        # Step 4: Generate response from LLM
        response = self.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_new_tokens=256,
            temperature=0.1
        )

        if self.verbose:
            print(f"   Tokens used: {response.tokens_used} (prompt: {response.prompt_tokens}, completion: {response.completion_tokens})")
            print(f"\n📝 LLM Response:")
            print(f"   {response.content[:200]}...")

        # Step 5: Parse and validate response
        available_ids = [e['id'] for e in compressed['elements']]
        parsed = self.response_parser.safe_parse(
            response,
            available_ids,
            verbose=self.verbose
        )

        if parsed is None:
            print("❌ Failed to parse or validate LLM response")
            return None

        # Step 6: Add full element data
        selected_id = parsed['id']
        selected_element = next(
            (e for e in element_snapshot.elements if e.id == selected_id),
            None
        )

        if selected_element is None:
            print(f"❌ Element {selected_id} not found in original snapshot")
            return None

        result = {
            "id": selected_id,
            "element": selected_element,
            "reasoning": parsed.get("reasoning", ""),
            "confidence": parsed.get("confidence", parsed.get("match_quality", "unknown")),
            "tokens_used": response.tokens_used,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens
        }

        if self.verbose:
            text_preview = selected_element.text[:50] if selected_element.text else "(no text)"
            print(f"\n✅ Selected Element:")
            print(f"   ID: {selected_id}")
            print(f"   Role: {selected_element.role}")
            print(f"   Text: {text_preview}")
            print(f"   BBox: {selected_element.bbox}")
            print(f"   Reasoning: {result['reasoning']}")

        return result
