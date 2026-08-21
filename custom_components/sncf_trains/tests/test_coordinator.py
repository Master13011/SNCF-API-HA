"""Tests for the SNCF data update coordinator."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_OUTSIDE_INTERVAL,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.sncf_trains.coordinator import SncfUpdateCoordinator


def _create_entry(
    *,
    subentries: dict | None = None,
    update_interval: int = 2,
    outside_interval: int = 60,
) -> ConfigEntry:
    """Create a config entry suitable for coordinator tests."""
    entry = MagicMock(spec=ConfigEntry)

    entry.data = {
        CONF_API_KEY: "test_api_key",
    }

    entry.options = {
        CONF_UPDATE_INTERVAL: update_interval,
        CONF_OUTSIDE_INTERVAL: outside_interval,
    }

    entry.subentries = subentries or {}

    return entry


def _create_subentry(
    *,
    title: str = "Paris → Lyon",
    departure: str = "stop_area:dep",
    arrival: str = "stop_area:arr",
    time_start: str = "07:00",
    time_end: str = "10:00",
) -> MagicMock:
    """Create a config subentry suitable for coordinator tests."""
    subentry = MagicMock()
    subentry.title = title
    subentry.data = {
        CONF_FROM: departure,
        CONF_TO: arrival,
        CONF_TIME_START: time_start,
        CONF_TIME_END: time_end,
    }
    return subentry


@pytest.mark.asyncio
async def test_coordinator_success(hass):
    """Test successful journey retrieval."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        return_value=[
            {
                "id": "journey_1",
                "nb_transfers": 0,
            },
            {
                "id": "journey_2",
                "nb_transfers": 0,
            },
        ]
    )

    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 21, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [
            {
                "id": "journey_1",
                "nb_transfers": 0,
            },
            {
                "id": "journey_2",
                "nb_transfers": 0,
            },
        ]
    }

    mock_api.fetch_journeys.assert_awaited_once()

    call_args = mock_api.fetch_journeys.await_args
    assert call_args.args[:2] == (
        "stop_area:dep",
        "stop_area:arr",
    )
    assert call_args.kwargs == {"count": 10}

    assert coordinator.update_interval == timedelta(minutes=2)


@pytest.mark.asyncio
async def test_coordinator_filters_journeys_with_transfers(hass):
    """Test that journeys with transfers are filtered out."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        return_value=[
            {
                "id": "direct",
                "nb_transfers": 0,
            },
            {
                "id": "with_transfer",
                "nb_transfers": 1,
            },
            {
                "id": "two_transfers",
                "nb_transfers": 2,
            },
            "invalid_journey",
            None,
        ]
    )

    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 21, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [
            {
                "id": "direct",
                "nb_transfers": 0,
            }
        ]
    }


@pytest.mark.asyncio
async def test_coordinator_empty_subentries(hass):
    """Test coordinator behavior when no subentries are configured."""
    entry = _create_entry()

    coordinator = SncfUpdateCoordinator(hass, entry)

    data = await coordinator._async_update_data()

    assert data == {}


@pytest.mark.asyncio
async def test_coordinator_api_returns_none(hass):
    """Test coordinator behavior when the API returns None."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value=None)

    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 21, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {}

    assert mock_api.fetch_journeys.await_count == 3


@pytest.mark.asyncio
async def test_coordinator_api_returns_invalid_data(hass):
    """Test coordinator behavior when the API returns invalid data."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value={"invalid": "data"})

    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 21, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {}

    mock_api.fetch_journeys.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_retries_runtime_error(hass):
    """Test coordinator retries after a runtime error."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        side_effect=[
            RuntimeError("API unavailable"),
            RuntimeError("API unavailable"),
            [
                {
                    "id": "journey_1",
                    "nb_transfers": 0,
                }
            ],
        ]
    )

    coordinator.api_client = mock_api

    with (
        patch(
            "custom_components.sncf_trains.coordinator.dt_util.now",
            return_value=datetime(2026, 8, 21, 8, 0),
        ),
        patch(
            "custom_components.sncf_trains.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [
            {
                "id": "journey_1",
                "nb_transfers": 0,
            }
        ]
    }

    assert mock_api.fetch_journeys.await_count == 3
    assert mock_sleep.await_count == 2
    mock_sleep.assert_any_await(2)


@pytest.mark.asyncio
async def test_coordinator_retries_timeout(hass):
    """Test coordinator retries after a timeout."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        side_effect=[
            asyncio.TimeoutError(),
            [
                {
                    "id": "journey_1",
                    "nb_transfers": 0,
                }
            ],
        ]
    )

    coordinator.api_client = mock_api

    with (
        patch(
            "custom_components.sncf_trains.coordinator.dt_util.now",
            return_value=datetime(2026, 8, 21, 8, 0),
        ),
        patch(
            "custom_components.sncf_trains.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [
            {
                "id": "journey_1",
                "nb_transfers": 0,
            }
        ]
    }

    assert mock_api.fetch_journeys.await_count == 2
    mock_sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_coordinator_retries_client_error(hass):
    """Test coordinator retries after a client error."""
    subentry = _create_subentry()

    entry = _create_entry(
        subentries={
            "subentry_1": subentry,
        }
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()

    from aiohttp import ClientError

    mock_api.fetch_journeys = AsyncMock(
        side_effect=[
            ClientError("network error"),
            [
                {
                    "id": "journey_1",
                    "nb_transfers": 0,
                }
            ],
        ]
    )

    coordinator.api_client = mock_api

    with (
        patch(
            "custom_components.sncf_trains.coordinator.dt_util.now",
            return_value=datetime(2026, 8, 21, 8, 0),
        ),
        patch(
            "custom_components.sncf_trains.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep,
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [
            {
                "id": "journey_1",
                "nb_transfers": 0,
            }
        ]
    }

    assert mock_api.fetch_journeys.await_count == 2
    mock_sleep.assert_awaited_once_with(2)


def test_coordinator_build_datetime_param(hass):
    """Test API datetime parameter generation."""
    entry = _create_entry()
    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 6, 30)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        result = coordinator._build_datetime_param(
            "07:00",
            "10:00",
        )

    assert result == "20260821T070000"


def test_coordinator_build_datetime_param_next_day(hass):
    """Test datetime generation when the requested range is tomorrow."""
    entry = _create_entry()
    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 11, 0)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        result = coordinator._build_datetime_param(
            "07:00",
            "10:00",
        )

    assert result == "20260822T070000"


def test_coordinator_adjust_update_interval_inside_window(hass):
    """Test fast update interval during the active time window."""
    entry = _create_entry(
        update_interval=5,
        outside_interval=30,
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 8, 0)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        interval = coordinator._adjust_update_interval(
            "07:00",
            "10:00",
        )

    assert interval == timedelta(minutes=5)


def test_coordinator_adjust_update_interval_outside_window(hass):
    """Test slow update interval outside the active time window."""
    entry = _create_entry(
        update_interval=5,
        outside_interval=30,
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 15, 0)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        interval = coordinator._adjust_update_interval(
            "07:00",
            "10:00",
        )

    assert interval == timedelta(minutes=30)


def test_coordinator_adjust_update_interval_pre_start(hass):
    """Test fast interval during the hour before the configured window."""
    entry = _create_entry(
        update_interval=5,
        outside_interval=30,
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 6, 30)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        interval = coordinator._adjust_update_interval(
            "07:00",
            "10:00",
        )

    assert interval == timedelta(minutes=5)


def test_coordinator_adjust_update_interval_crosses_midnight(hass):
    """Test update interval for a time range crossing midnight."""
    entry = _create_entry(
        update_interval=5,
        outside_interval=30,
    )

    coordinator = SncfUpdateCoordinator(hass, entry)

    current_time = datetime(2026, 8, 21, 23, 30)

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=current_time,
    ):
        interval = coordinator._adjust_update_interval(
            "23:00",
            "02:00",
        )

    assert interval == timedelta(minutes=5)
