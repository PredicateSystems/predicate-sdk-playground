from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import pytest

from overlay_utils import dismiss_overlays_before_agent


@pytest.mark.asyncio
async def test_dismiss_overlays_before_agent_passes_use_api_through() -> None:
    dismiss_overlays = AsyncMock(return_value=object())

    runtime = object()
    browser = object()

    with patch("overlay_utils.dismiss_overlays", dismiss_overlays):
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
