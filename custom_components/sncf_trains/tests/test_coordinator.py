import pytest
from unittest.mock import AsyncMock
from datetime import timedelta
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sncf_trains.coordinator import SncfUpdateCoordinator


@pytest.mark.asyncio
async def test_coordinator_success(hass):
    """Test coordinator fetches journeys successfully."""
    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value=[{"id": "j1"}])

    coordinator = SncfUpdateCoordinator(
        hass=hass,
        api_client=mock_api,
        departure="stop_area:dep",
        arrival="stop_area:arr",
        time_start="06:00",
        time_end="09:00",
        update_interval=5,
        outside_interval=30,
    )

    data = await coordinator._async_update_data()
    assert data == [{"id": "j1"}]
    mock_api.fetch_journeys.assert_called_once()
    assert isinstance(coordinator.update_interval, timedelta)


@pytest.mark.asyncio
async def test_coordinator_api_failure(hass):
    """Test coordinator raises UpdateFailed when API fails."""
    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(side_effect=Exception("API error"))

    coordinator = SncfUpdateCoordinator(
        hass=hass,
        api_client=mock_api,
        departure="stop_area:dep",
        arrival="stop_area:arr",
        time_start="06:00",
        time_end="09:00",
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_adjust_interval(hass):
    """Test that update interval adjusts inside and outside time range."""

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value=[{"id": "j1"}])

    coordinator = SncfUpdateCoordinator(
        hass=hass,
        api_client=mock_api,
        departure="stop_area:dep",
        arrival="stop_area:arr",
        time_start="00:00",
        time_end="23:59",
        update_interval=5,
        outside_interval=30,
    )

    # Forcing inside time range (always true here)
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(minutes=5)

    # Fake outside range by setting opposite times
    coordinator.time_start = "23:59"
    coordinator.time_end = "00:00"

    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(minutes=30)


