"""
Domain-Specific Heuristics for Generic Browser Agent Demo.

This module provides pluggable heuristics for different website types.
Heuristics help the executor find elements without LLM calls for common
patterns, improving speed and reliability.

The SDK's PlannerExecutorAgent accepts an `intent_heuristics` parameter
that implements the IntentHeuristics protocol:
- find_element_for_intent(intent, elements, url, goal) -> element_id | None
- priority_order() -> list[str]

When heuristics return an element ID, the LLM executor is skipped,
saving tokens and reducing latency.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IntentHeuristics(Protocol):
    """
    Protocol for domain-specific element selection heuristics.

    Implement this protocol to add custom heuristics for your site type.
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        """
        Find element ID for a given intent.

        Args:
            intent: Intent hint from the plan step (e.g., "add_to_cart")
            elements: List of snapshot elements with id, role, text, etc.
            url: Current page URL
            goal: Human-readable goal for context

        Returns:
            Element ID if found, None to fall back to LLM executor
        """
        ...

    def priority_order(self) -> list[str]:
        """Return intent patterns in priority order."""
        ...


# =============================================================================
# E-Commerce Heuristics
# =============================================================================


class EcommerceHeuristics:
    """
    Domain-specific heuristics for e-commerce sites.

    Handles common patterns like:
    - Search box detection
    - Add to cart buttons
    - Checkout/proceed buttons
    - Product links in search results
    - Modal dismissal (cookie consent, popups)
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        """Find element ID using e-commerce heuristics."""
        intent_lower = intent.lower().replace("-", "_").replace(" ", "_")

        # Search box
        if "search" in intent_lower and ("box" in intent_lower or "input" in intent_lower):
            return self._find_search_box(elements)

        # Add to cart
        if "add" in intent_lower and "cart" in intent_lower:
            return self._find_add_to_cart(elements)

        # Checkout / proceed
        if "checkout" in intent_lower or "proceed" in intent_lower:
            return self._find_checkout_button(elements)

        # Product link
        if "product" in intent_lower and (
            "first" in intent_lower or "link" in intent_lower or "title" in intent_lower
        ):
            return self._find_first_product_link(elements, url)

        # Close / dismiss modal
        if "close" in intent_lower or "dismiss" in intent_lower or "no_thanks" in intent_lower:
            return self._find_dismiss_button(elements)

        # Cookie consent
        if "cookie" in intent_lower or ("accept" in intent_lower and "consent" in goal.lower()):
            return self._find_cookie_consent(elements)

        return None

    def priority_order(self) -> list[str]:
        """Return intent patterns in priority order."""
        return [
            "add_to_cart",
            "checkout",
            "proceed_to_checkout",
            "search_box",
            "first_product_link",
            "close",
            "dismiss",
            "no_thanks",
            "accept_cookies",
        ]

    def _find_search_box(self, elements: list[Any]) -> int | None:
        """Find search box element."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"searchbox", "textbox", "combobox"}:
                continue
            text = (getattr(el, "text", "") or "").lower()
            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0

            prefers_search = 0 if "search" in text else 1
            candidates.append((not in_viewport, prefers_search, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][4]

    def _find_add_to_cart(self, elements: list[Any]) -> int | None:
        """Find 'Add to Cart' button."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "add to cart" not in text and "add to bag" not in text:
                continue
            if "buy now" in text:
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_checkout_button(self, elements: list[Any]) -> int | None:
        """Find checkout/proceed button, or cart icon as fallback."""
        candidates = []
        cart_icon_candidates = []

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"button", "link"}:
                continue
            text = (getattr(el, "text", "") or "").lower()
            aria_label = (getattr(el, "aria_label", "") or getattr(el, "ariaLabel", "") or "").lower()

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0

            # Primary: checkout/proceed buttons
            if "checkout" in text or "proceed" in text or "view cart" in text or "view bag" in text:
                if "add to cart" not in text and "buy now" not in text:
                    is_checkout = 0 if "checkout" in text else 1
                    candidates.append((not in_viewport, is_checkout, doc_y, -importance, el.id))
                    continue

            # Fallback: cart icon button (usually in header)
            # Look for buttons with cart-related aria-label or text
            cart_patterns = ["open cart", "shopping cart", "cart", "bag", "basket"]
            if any(p in text for p in cart_patterns) or any(p in aria_label for p in cart_patterns):
                # Prefer buttons higher on page (in header)
                cart_icon_candidates.append((doc_y, -importance, el.id))

        # Return checkout button if found
        if candidates:
            candidates.sort()
            return candidates[0][4]

        # Fallback to cart icon if no checkout button found
        if cart_icon_candidates:
            cart_icon_candidates.sort()
            return cart_icon_candidates[0][2]

        return None

    def _find_first_product_link(self, elements: list[Any], url: str) -> int | None:
        """Find first product link in search results."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "link":
                continue
            href = (getattr(el, "href", "") or "").lower()

            # Common product URL patterns
            if not any(p in href for p in ["/dp/", "/gp/product/", "/product/", "/products/", "/p/"]):
                continue
            # Exclude filters
            if "refinements=" in href or "rh=" in href:
                continue

            text = (getattr(el, "text", "") or "").strip()
            if not text or len(text) < 3:
                continue

            # Skip non-product items
            text_lower = text.lower()
            skip_patterns = [
                "sponsored", "free shipping", "prime", "filter", "sort by",
                "see all", "show more"
            ]
            if any(p in text_lower for p in skip_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_dismiss_button(self, elements: list[Any]) -> int | None:
        """Find dismiss/close/no thanks button."""
        candidates = []
        dismiss_patterns = ["no thanks", "close", "dismiss", "cancel", "not now", "skip", "x", "×"]

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower().strip()
            if not any(p == text or p in text for p in dismiss_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    def _find_cookie_consent(self, elements: list[Any]) -> int | None:
        """Find cookie consent accept button."""
        candidates = []
        accept_patterns = ["accept", "accept all", "allow", "agree", "ok", "got it", "i agree"]

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if not any(p in text for p in accept_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]


# =============================================================================
# Search / Reference Heuristics
# =============================================================================


class SearchHeuristics:
    """
    Heuristics for search engines and reference sites.

    Handles patterns like:
    - Search input fields
    - Search result links
    - Navigation links
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        intent_lower = intent.lower().replace("-", "_").replace(" ", "_")

        if "search" in intent_lower and ("box" in intent_lower or "input" in intent_lower):
            return self._find_search_input(elements)

        if "result" in intent_lower and "first" in intent_lower:
            return self._find_first_result(elements)

        return None

    def priority_order(self) -> list[str]:
        return ["search_input", "first_result"]

    def _find_search_input(self, elements: list[Any]) -> int | None:
        """Find search input field."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"searchbox", "textbox", "combobox"}:
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _find_first_result(self, elements: list[Any]) -> int | None:
        """Find first search result link."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "link":
                continue

            text = (getattr(el, "text", "") or "").strip()
            if not text or len(text) < 5:
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            doc_y = getattr(el, "doc_y", None) or 1e9
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, doc_y, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]


# =============================================================================
# Form Heuristics
# =============================================================================


class FormHeuristics:
    """
    Heuristics for form interactions.

    Handles patterns like:
    - Form field detection by label
    - Submit button detection
    - Checkbox/radio handling
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        intent_lower = intent.lower().replace("-", "_").replace(" ", "_")

        if "submit" in intent_lower:
            return self._find_submit_button(elements)

        if "email" in intent_lower and ("field" in intent_lower or "input" in intent_lower):
            return self._find_email_field(elements)

        return None

    def priority_order(self) -> list[str]:
        return ["submit_button", "email_field", "name_field"]

    def _find_submit_button(self, elements: list[Any]) -> int | None:
        """Find form submit button."""
        candidates = []
        submit_patterns = ["submit", "send", "sign up", "subscribe", "continue", "next"]

        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if not any(p in text for p in submit_patterns):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _find_email_field(self, elements: list[Any]) -> int | None:
        """Find email input field."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"textbox", "combobox"}:
                continue

            text = (getattr(el, "text", "") or "").lower()
            nearby = (getattr(el, "nearby_text", "") or "").lower()
            placeholder = (getattr(el, "placeholder", "") or "").lower()

            if not any("email" in s for s in [text, nearby, placeholder]):
                continue

            in_viewport = bool(getattr(el, "in_viewport", True))
            importance = getattr(el, "importance", 0) or 0
            candidates.append((not in_viewport, -importance, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]


# =============================================================================
# Combined Heuristics
# =============================================================================


class CombinedHeuristics:
    """
    Combines multiple domain-specific heuristics.

    Tries each heuristic set in order until one returns a match.
    """

    def __init__(self, heuristics: list[IntentHeuristics] | None = None):
        """
        Initialize with a list of heuristics to try.

        Args:
            heuristics: List of heuristics to try in order.
                        Defaults to [EcommerceHeuristics, SearchHeuristics, FormHeuristics]
        """
        self._heuristics = heuristics or [
            EcommerceHeuristics(),
            SearchHeuristics(),
            FormHeuristics(),
        ]

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        """Try each heuristic until one returns a match."""
        for heuristic in self._heuristics:
            result = heuristic.find_element_for_intent(intent, elements, url, goal)
            if result is not None:
                return result
        return None

    def priority_order(self) -> list[str]:
        """Combine priority orders from all heuristics."""
        combined = []
        seen = set()
        for heuristic in self._heuristics:
            for pattern in heuristic.priority_order():
                if pattern not in seen:
                    seen.add(pattern)
                    combined.append(pattern)
        return combined


# =============================================================================
# Factory Function
# =============================================================================


def get_heuristics_for_domain(domain_hints: tuple[str, ...] | None = None) -> IntentHeuristics:
    """
    Get appropriate heuristics based on domain hints.

    Args:
        domain_hints: Tuple of domain hints (e.g., ("ecommerce", "amazon"))

    Returns:
        IntentHeuristics implementation

    Example:
        heuristics = get_heuristics_for_domain(("ecommerce",))
    """
    if not domain_hints:
        return CombinedHeuristics()

    hints = set(h.lower() for h in domain_hints)

    if hints & {"ecommerce", "shopping", "amazon", "ebay", "walmart", "target"}:
        return EcommerceHeuristics()

    if hints & {"search", "google", "reference", "wikipedia"}:
        return SearchHeuristics()

    if hints & {"forms", "contact", "signup"}:
        return FormHeuristics()

    # Default: combined heuristics
    return CombinedHeuristics()
