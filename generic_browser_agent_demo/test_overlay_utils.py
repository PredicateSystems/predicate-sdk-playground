"""Tests for overlay dismissal utilities (now in SDK)."""

from unittest.mock import AsyncMock, patch

import pytest

from predicate.overlay_dismissal import dismiss_overlays_before_agent


@pytest.mark.asyncio
async def test_dismiss_overlays_before_agent_passes_use_api_through() -> None:
    """Test that dismiss_overlays_before_agent passes parameters correctly."""
    dismiss_overlays = AsyncMock(return_value=object())

    runtime = object()
    browser = object()

    with patch("predicate.overlay_dismissal.dismiss_overlays", dismiss_overlays):
        result = await dismiss_overlays_before_agent(
            runtime,
            browser,
            use_api=False,
            verbose=True,
        )

    assert result is dismiss_overlays.return_value
    dismiss_overlays.assert_awaited_once_with(
        runtime,
        browser,
        max_rounds=3,
        snapshot_limit=100,
        max_clicks_per_round=4,
        use_api=False,
        max_seconds=12.0,
        verbose=True,
    )
