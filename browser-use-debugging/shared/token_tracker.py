"""
Token usage tracking for LLM agent demos.

Copied from: sentience-sdk-playground/amazon_shopping/shared/token_tracker.py
to keep demo visuals consistent across playground projects.
"""

from __future__ import annotations

from typing import Any, Dict, List


class TokenTracker:
    """Track token usage across multiple LLM interactions."""

    def __init__(self, demo_name: str):
        self.demo_name = demo_name
        self.interactions: List[Dict[str, Any]] = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0

    def log_interaction(self, scene: str, prompt_tokens: int, completion_tokens: int):
        """Log a single LLM interaction."""
        total = prompt_tokens + completion_tokens
        self.interactions.append(
            {
                "scene": scene,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total": total,
            }
        )
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += total

        print(
            f"  Token usage: {total} (prompt: {prompt_tokens}, completion: {completion_tokens})"
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get complete token usage summary."""
        return {
            "demo_name": self.demo_name,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "interactions": self.interactions,
            "average_per_scene": self.total_tokens / len(self.interactions)
            if self.interactions
            else 0,
        }

    def save_to_file(self, filepath: str):
        """Save summary to JSON file."""
        import json

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.get_summary(), f, indent=2)
        print(f"Token summary saved to: {filepath}")

