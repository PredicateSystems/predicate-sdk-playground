"""
Task Definitions for Generic Browser Agent Demo.

This module defines task categories and provides pre-built task templates
that work across different website types. The SDK's PlannerExecutorAgent
can handle all of these categories with the same architecture.

Task Categories (from WebBench):
- READ: Extract information from pages (prices, reviews, listings)
- CREATE: Submit forms, post content, add items to cart
- UPDATE: Modify existing data (profile, cart quantity, settings)
- DELETE: Remove items (wishlist, cart, bookmarks)
- TRANSACTION: Multi-step flows (shopping, booking, checkout)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskCategory(str, Enum):
    """Task categories based on WebBench taxonomy."""

    READ = "read"  # Information extraction
    CREATE = "create"  # Form submission, content creation
    UPDATE = "update"  # Modify existing data
    DELETE = "delete"  # Remove items
    TRANSACTION = "transaction"  # Multi-step flows (shopping, checkout)


@dataclass
class TaskDefinition:
    """
    Definition of a browser automation task.

    Attributes:
        task_id: Unique identifier for the task
        starting_url: URL to begin the automation
        task: Natural language description of what to accomplish
        category: Task category (READ, CREATE, UPDATE, DELETE, TRANSACTION)
        success_predicates: Optional predicates to verify task completion
        domain_hints: Optional hints about the website domain (e.g., "ecommerce", "social")
        max_steps: Maximum steps before giving up
        enable_recovery: Whether to enable recovery on failure
    """

    task_id: str
    starting_url: str
    task: str
    category: TaskCategory = TaskCategory.READ
    success_predicates: list[dict[str, Any]] = field(default_factory=list)
    domain_hints: tuple[str, ...] = ()
    max_steps: int = 30
    enable_recovery: bool = True

    @classmethod
    def create(
        cls,
        starting_url: str,
        task: str,
        category: TaskCategory = TaskCategory.READ,
        **kwargs,
    ) -> "TaskDefinition":
        """
        Factory method to create a TaskDefinition with auto-generated ID.

        Example:
            task = TaskDefinition.create(
                starting_url="https://amazon.com",
                task="Search for laptop and add first result to cart",
                category=TaskCategory.TRANSACTION,
            )
        """
        task_id = f"{category.value}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        return cls(
            task_id=task_id,
            starting_url=starting_url,
            task=task,
            category=category,
            **kwargs,
        )


# =============================================================================
# Pre-built Task Templates
# =============================================================================

# Shopping / E-commerce Tasks
SHOPPING_TASKS = {
    "amazon_search_add_to_cart": TaskDefinition(
        task_id="amazon-add-to-cart",
        starting_url="https://www.amazon.com",
        task="Search for 'wireless mouse' and add the first result to cart, then proceed to checkout.",
        category=TaskCategory.TRANSACTION,
        success_predicates=[
            {"predicate": "any_of", "args": [
                {"predicate": "url_contains", "args": ["/cart"]},
                {"predicate": "url_contains", "args": ["checkout"]},
                {"predicate": "url_contains", "args": ["signin"]},
            ]},
        ],
        domain_hints=("ecommerce", "amazon"),
    ),
    "lifeisgood_shopping": TaskDefinition(
        task_id="lifeisgood-shopping",
        starting_url="https://www.lifeisgood.com",
        task="Search for 'Rainbow Trout Trucker' hat, select a size, add it to cart, and proceed to checkout.",
        category=TaskCategory.TRANSACTION,
        success_predicates=[
            {"predicate": "url_contains", "args": ["checkout"]},
        ],
        domain_hints=("ecommerce",),
    ),
    "bestbuy_product_search": TaskDefinition(
        task_id="bestbuy-search",
        starting_url="https://www.bestbuy.com",
        task="Search for '4K TV' and extract the names and prices of the first 3 products.",
        category=TaskCategory.READ,
        domain_hints=("ecommerce",),
    ),
}

# Information Extraction Tasks
READ_TASKS = {
    "wikipedia_extract": TaskDefinition(
        task_id="wikipedia-extract",
        starting_url="https://en.wikipedia.org",
        task="Search for 'Artificial Intelligence' and extract the first paragraph of the article.",
        category=TaskCategory.READ,
        domain_hints=("reference",),
    ),
    "news_headlines": TaskDefinition(
        task_id="news-headlines",
        starting_url="https://news.ycombinator.com",
        task="Extract the titles and point counts of the top 5 stories on the front page.",
        category=TaskCategory.READ,
        domain_hints=("news",),
    ),
    "recipe_search": TaskDefinition(
        task_id="recipe-search",
        starting_url="https://www.allrecipes.com",
        task="Search for 'chocolate chip cookies' and extract the cooking time and serving size from the first recipe.",
        category=TaskCategory.READ,
        domain_hints=("recipes",),
    ),
    "weather_lookup": TaskDefinition(
        task_id="weather-lookup",
        starting_url="https://weather.com",
        task="Look up the current weather and 5-day forecast for New York City.",
        category=TaskCategory.READ,
        domain_hints=("weather",),
    ),
}

# Form Submission Tasks
CREATE_TASKS = {
    "contact_form": TaskDefinition(
        task_id="contact-form",
        starting_url="https://example.com/contact",
        task="Fill out the contact form with name 'Test User', email 'test@example.com', and message 'This is a test inquiry.'",
        category=TaskCategory.CREATE,
        domain_hints=("forms",),
    ),
    "newsletter_signup": TaskDefinition(
        task_id="newsletter-signup",
        starting_url="https://example.com",
        task="Find the newsletter signup form and subscribe with email 'demo@example.com'.",
        category=TaskCategory.CREATE,
        domain_hints=("forms",),
    ),
}

# Travel / Booking Tasks
TRAVEL_TASKS = {
    "flight_search": TaskDefinition(
        task_id="flight-search",
        starting_url="https://www.google.com/travel/flights",
        task="Search for round-trip flights from San Francisco to New York for next weekend and list the 3 cheapest options.",
        category=TaskCategory.READ,
        domain_hints=("travel", "flights"),
    ),
    "hotel_search": TaskDefinition(
        task_id="hotel-search",
        starting_url="https://www.booking.com",
        task="Search for hotels in Paris for 2 adults, check-in next Friday, check-out Sunday, and extract the top 3 rated hotels.",
        category=TaskCategory.READ,
        domain_hints=("travel", "hotels"),
    ),
}

# Social / Content Tasks
SOCIAL_TASKS = {
    "github_repo_info": TaskDefinition(
        task_id="github-repo",
        starting_url="https://github.com",
        task="Search for 'react' and extract the star count, fork count, and description of the first repository.",
        category=TaskCategory.READ,
        domain_hints=("social", "developer"),
    ),
    "reddit_search": TaskDefinition(
        task_id="reddit-search",
        starting_url="https://www.reddit.com",
        task="Search for 'machine learning' and list the titles and upvote counts of the top 5 posts.",
        category=TaskCategory.READ,
        domain_hints=("social",),
    ),
}

# All tasks combined for easy access
ALL_TASKS = {
    **SHOPPING_TASKS,
    **READ_TASKS,
    **CREATE_TASKS,
    **TRAVEL_TASKS,
    **SOCIAL_TASKS,
}


def get_task(task_key: str) -> TaskDefinition:
    """
    Get a pre-defined task by key.

    Args:
        task_key: Key from ALL_TASKS (e.g., "amazon_search_add_to_cart")

    Returns:
        TaskDefinition instance

    Raises:
        KeyError: If task_key not found
    """
    if task_key not in ALL_TASKS:
        available = ", ".join(ALL_TASKS.keys())
        raise KeyError(f"Task '{task_key}' not found. Available tasks: {available}")
    return ALL_TASKS[task_key]


def list_tasks() -> dict[str, list[str]]:
    """
    List all available tasks grouped by category.

    Returns:
        Dictionary mapping category names to lists of task keys
    """
    by_category: dict[str, list[str]] = {}
    for key, task in ALL_TASKS.items():
        cat = task.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(key)
    return by_category


def create_custom_task(
    starting_url: str,
    task: str,
    category: TaskCategory = TaskCategory.READ,
    **kwargs,
) -> TaskDefinition:
    """
    Create a custom task definition.

    This is the recommended way to create tasks for your specific use case.

    Args:
        starting_url: URL to begin the automation
        task: Natural language description of the task
        category: Task category (default: READ)
        **kwargs: Additional TaskDefinition fields

    Returns:
        TaskDefinition instance

    Example:
        task = create_custom_task(
            starting_url="https://mysite.com",
            task="Find the pricing page and extract all plan prices",
            category=TaskCategory.READ,
            domain_hints=("saas",),
        )
    """
    return TaskDefinition.create(
        starting_url=starting_url,
        task=task,
        category=category,
        **kwargs,
    )
