"""Tests for the SNCF data update coordinator."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
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
        CONF_DEPARTURE_NAME: "Paris",
        CONF_ARRIVAL_NAME: "Lyon",
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

    # 3 realtime attempts + 1 theoretical-schedule fallback (no date gate)
    assert mock_api.fetch_journeys.await_count == 4


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


@pytest.mark.asyncio
async def test_coordinator_uses_theoretical_schedule_after_realtime_is_empty(hass):
    """Use base_schedule when realtime has no journeys after migration date."""
    subentry = _create_subentry()
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(side_effect=[[], [{"id": "scheduled", "nb_transfers": 0}]])
    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 11, 24, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {"subentry_1": [{"id": "scheduled", "nb_transfers": 0}]}
    assert mock_api.fetch_journeys.await_count == 2
    assert mock_api.fetch_journeys.await_args_list[0].kwargs == {"count": 10}
    assert mock_api.fetch_journeys.await_args_list[1].kwargs == {
        "count": 10,
        "data_freshness": "base_schedule",
    }
    mock_api.search_stations.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_resolves_new_station_ids_after_old_ids_fail(hass):
    """Resolve the saved station names and retry with new repository IDs."""
    subentry = _create_subentry()
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        side_effect=[
            [],  # Legacy IDs, realtime
            [],  # Legacy IDs, theoretical schedule
            [{"id": "new_ids_journey", "nb_transfers": 0}],  # New IDs, realtime
        ]
    )
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [{"id": "stop_area:new_paris", "name": "Paris"}],
            [{"id": "stop_area:new_lyon", "name": "Lyon"}],
        ]
    )
    coordinator.api_client = mock_api

    with (
        patch(
            "custom_components.sncf_trains.coordinator.dt_util.now",
            return_value=datetime(2026, 11, 24, 8, 0),
        ),
        patch.object(
            hass.config_entries, "async_update_subentry"
        ) as mock_update_subentry,
    ):
        data = await coordinator._async_update_data()

    assert data == {
        "subentry_1": [{"id": "new_ids_journey", "nb_transfers": 0}]
    }
    # The resolved IDs are saved in the subentry (survive restarts)
    mock_update_subentry.assert_called_once()
    saved = mock_update_subentry.call_args.kwargs["data"]
    assert saved[CONF_FROM] == "stop_area:new_paris"
    assert saved[CONF_TO] == "stop_area:new_lyon"
    assert mock_api.search_stations.await_args_list[0].args == ("Paris",)
    assert mock_api.search_stations.await_args_list[1].args == ("Lyon",)
    assert mock_api.fetch_journeys.await_args_list[2].args[:2] == (
        "stop_area:new_paris",
        "stop_area:new_lyon",
    )


@pytest.mark.asyncio
async def test_coordinator_resolves_station_names_without_case_or_accent_sensitivity(hass):
    """Station matching tolerates case, accents and whitespace differences."""
    coordinator = SncfUpdateCoordinator(hass, _create_entry())
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [{"id": "stop_area:paris", "name": "PARIS"}],
            [{"id": "stop_area:lyon", "name": "Lyon Part-Dieu"}],
        ]
    )
    coordinator.api_client = mock_api

    result = await coordinator._resolve_station_ids(" Paris ", "Lyon Part-Dieu")

    assert result == ("stop_area:paris", "stop_area:lyon")
    assert await coordinator._resolve_station_ids(" Paris ", "Lyon Part-Dieu") == result
    assert mock_api.search_stations.await_count == 2  # cached on second call


@pytest.mark.asyncio
async def test_coordinator_does_not_choose_ambiguous_station_result(hass):
    """Do not silently pick a similar but non-identical station name."""
    coordinator = SncfUpdateCoordinator(hass, _create_entry())
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        return_value=[{"id": "stop_area:paris_all", "name": "Paris (toutes gares)"}]
    )
    coordinator.api_client = mock_api

    result = await coordinator._resolve_station_ids("Paris", "Lyon")

    assert result is None
    mock_api.search_stations.assert_awaited_once_with("Paris")


@pytest.mark.asyncio
async def test_coordinator_fallback_not_gated_by_date(hass):
    """The theoretical-schedule fallback no longer depends on a fixed date."""
    subentry = _create_subentry()
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        side_effect=[[], [{"id": "scheduled", "nb_transfers": 0}]]
    )
    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 21, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {"subentry_1": [{"id": "scheduled", "nb_transfers": 0}]}
    assert mock_api.fetch_journeys.await_args_list[1].kwargs["data_freshness"] == (
        "base_schedule"
    )


@pytest.mark.asyncio
async def test_coordinator_fallback_suspended_after_failure(hass):
    """A failed fallback is not retried until the delay has elapsed."""
    subentry = _create_subentry()
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value=[])
    mock_api.search_stations = AsyncMock(return_value=[])
    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 11, 24, 8, 0),
    ):
        await coordinator._async_update_data()
        calls_after_first = mock_api.fetch_journeys.await_count
        searches_after_first = mock_api.search_stations.await_count
        assert calls_after_first == 2  # realtime + theoretical
        assert searches_after_first == 1  # departure lookup fails, stops there

        # Second refresh: only the realtime call, no fallback, no search
        await coordinator._async_update_data()
        assert mock_api.fetch_journeys.await_count == calls_after_first + 1
        assert mock_api.search_stations.await_count == searches_after_first

        # Once the delay has elapsed the fallback is attempted again
        coordinator._fallback_retry_at["subentry_1"] = 0.0
        await coordinator._async_update_data()
        assert mock_api.search_stations.await_count == searches_after_first + 1


@pytest.mark.asyncio
async def test_coordinator_fallback_resets_after_success(hass):
    """A successful fallback clears the suspension."""
    subentry = _create_subentry()
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)
    coordinator._fallback_retry_at["subentry_1"] = 0.0

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(
        side_effect=[[], [{"id": "scheduled", "nb_transfers": 0}]]
    )
    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 11, 24, 8, 0),
    ):
        await coordinator._async_update_data()

    assert "subentry_1" not in coordinator._fallback_retry_at


@pytest.mark.asyncio
async def test_coordinator_fallback_warns_when_names_are_only_ids(hass):
    """Without a real station name, new IDs cannot be resolved."""
    subentry = _create_subentry()
    subentry.data[CONF_DEPARTURE_NAME] = subentry.data[CONF_FROM]
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_journeys = AsyncMock(return_value=[])
    coordinator.api_client = mock_api

    with patch(
        "custom_components.sncf_trains.coordinator.dt_util.now",
        return_value=datetime(2026, 11, 24, 8, 0),
    ):
        data = await coordinator._async_update_data()

    assert data == {"subentry_1": []}
    mock_api.search_stations.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_backfills_missing_station_names(hass):
    """Subentries holding only IDs get their station names saved."""
    subentry = _create_subentry()
    subentry.data[CONF_DEPARTURE_NAME] = subentry.data[CONF_FROM]  # legacy: ID as name
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_station_name = AsyncMock(return_value="Paris Gare de Lyon (Paris)")
    coordinator.api_client = mock_api

    with patch.object(
        hass.config_entries, "async_update_subentry"
    ) as mock_update_subentry:
        await coordinator._async_backfill_station_names()

    # Only the departure (ID used as name) is looked up; arrival already has a name
    mock_api.fetch_station_name.assert_awaited_once_with("stop_area:dep")
    saved = mock_update_subentry.call_args.kwargs["data"]
    assert saved[CONF_DEPARTURE_NAME] == "Paris Gare de Lyon (Paris)"
    assert saved[CONF_ARRIVAL_NAME] == "Lyon"


@pytest.mark.asyncio
async def test_coordinator_backfill_ignores_lookup_failures(hass):
    """A failed name lookup never breaks setup."""
    subentry = _create_subentry()
    subentry.data[CONF_ARRIVAL_NAME] = subentry.data[CONF_TO]
    entry = _create_entry(subentries={"subentry_1": subentry})
    coordinator = SncfUpdateCoordinator(hass, entry)

    mock_api = AsyncMock()
    mock_api.fetch_station_name = AsyncMock(return_value=None)
    coordinator.api_client = mock_api

    with patch.object(
        hass.config_entries, "async_update_subentry"
    ) as mock_update_subentry:
        await coordinator._async_backfill_station_names()

    mock_update_subentry.assert_not_called()


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


@pytest.mark.asyncio
async def test_enrichment_survives_departure_and_refreshes_arrival_track(hass):
    coordinator = SncfUpdateCoordinator(hass, _create_entry())
    from homeassistant.util import dt as dt_util

    now = dt_util.parse_datetime("2026-11-25T16:25:00+00:00")
    departure = "2026-11-25T16:16:00+00:00"
    arrival = "2026-11-25T16:51:00+00:00"

    def journey():
        return {
            "trip_short_name": "17629",
            "arrival_uic": "87723478",
            "departure_date_time": departure,
            "arrival_date_time": arrival,
            "sections": [{"type": "public_transport",
                          "base_departure_date_time": departure}],
        }

    def response(payload, status=200):
        context = MagicMock()
        context.__aenter__.return_value.status = status
        context.__aenter__.return_value.json = AsyncMock(return_value=payload)
        return context

    item = {"trainNumber": "17629", "circulationId": "test-course",
            "scheduledTime": departure}
    detail = {
        "scheduledTime": departure,
        "JourneyStop": [
            {"uic": "0087723197", "scheduledTime": departure,
             "platform": {"track": "J"}},
            {"uic": "0087723478", "scheduledTime": arrival,
             "platform": {"track": "A"}},
        ],
        "composition": {"element": [
            {"numeroAffectation": "0KSRA-Z24633"},
            {"numeroAffectation": "0KSRA-Z24757"},
        ]},
    }
    session = MagicMock()
    session.get.side_effect = [
        response([item]), response([{**detail, "JourneyStop": detail["JourneyStop"][:1]}]),
        response([]), response([detail]),
        response([], 503), response([], 503),
    ]
    with (
        patch("custom_components.sncf_trains.coordinator.dt_util.now", return_value=now),
        patch("custom_components.sncf_trains.coordinator.async_get_clientsession", return_value=session),
    ):
        first = journey()
        await coordinator._enrich_journeys([first], "0087723197")
        assert first["train_units"] == 2
        second = journey()
        await coordinator._enrich_journeys([second], "0087723197")
        assert second["arrival_platform_track"] == "A"
        assert "test-course" in session.get.call_args.args[0]
        third = journey()
        await coordinator._enrich_journeys([third], "0087723197")
        assert third["train_units"] == 2
        assert third["platform_track"] == "J"
        assert third["arrival_platform_track"] == "A"
        cancelled = {**journey(), "status": "NO_SERVICE"}
        await coordinator._enrich_journeys([cancelled], "0087723197")
        assert not coordinator._circulation_cache
        assert "train_units" not in cancelled