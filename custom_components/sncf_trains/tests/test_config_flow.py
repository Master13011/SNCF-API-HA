"""Tests for the SNCF config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_ARRIVAL_CITY,
    CONF_ARRIVAL_STATION,
    CONF_DEPARTURE_CITY,
    CONF_DEPARTURE_STATION,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TRAIN_COUNT,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_config_flow_happy_path(hass):
    """Test the main config flow with a valid API key."""
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        return_value=[
            {
                "id": "stop_area:dep",
                "name": "Paris Gare de Lyon",
            }
        ]
    )

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "valid_key"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Trains SNCF"
    assert result["data"] == {CONF_API_KEY: "valid_key"}
    assert result["result"].unique_id == "sncf_trains"


@pytest.mark.asyncio
async def test_config_flow_invalid_api_key(hass):
    """Test config flow with an invalid API key."""
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(return_value=None)

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "bad_key"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_config_flow_duplicate_entry(hass):
    """Test that the integration cannot be configured twice."""
    existing_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "existing_key"},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
    )
    existing_entry.add_to_hass(hass)

    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(return_value=[{"id": "stop_area:dep"}])

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new_key"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_train_subentry_happy_path(hass):
    """Test creation of a train subentry."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "valid_key"},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
    )
    entry.add_to_hass(hass)

    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [
                {
                    "id": "stop_area:dep",
                    "name": "Paris Gare de Lyon",
                }
            ],
            [
                {
                    "id": "stop_area:arr",
                    "name": "Lyon Part Dieu",
                }
            ],
        ]
    )

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.subentries.flow.async_init(
            (entry.entry_id, "train"),
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "departure_city"

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_CITY: "Paris",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "departure_station"

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_STATION: "stop_area:dep",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "arrival_city"

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ARRIVAL_CITY: "Lyon",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "arrival_station"

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ARRIVAL_STATION: "stop_area:arr",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "time_range"

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_TIME_START: "07:00",
                CONF_TIME_END: "10:00",
                CONF_TRAIN_COUNT: 5,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == (
        "Trajet: Paris Gare de Lyon → Lyon Part Dieu (07:00 - 10:00)"
    )

    assert result["data"] == {
        "from": "stop_area:dep",
        "to": "stop_area:arr",
        "departure_name": "Paris Gare de Lyon",
        "arrival_name": "Lyon Part Dieu",
        "time_start": "07:00",
        "time_end": "10:00",
        "train_count": 5,
    }

    assert result["unique_id"] == (
        "stop_area:dep_stop_area:arr_07:00_10:00"
    )


@pytest.mark.asyncio
async def test_train_subentry_no_departure_stations(hass):
    """Test train subentry when no departure station is found."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "valid_key"},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
    )
    entry.add_to_hass(hass)

    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(return_value=None)

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.subentries.flow.async_init(
            (entry.entry_id, "train"),
            context={"source": config_entries.SOURCE_USER},
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_CITY: "Paris",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "departure_city"
    assert result["errors"]["base"] == "no_stations"


@pytest.mark.asyncio
async def test_train_subentry_no_arrival_stations(hass):
    """Test train subentry when no arrival station is found."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "valid_key"},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
    )
    entry.add_to_hass(hass)

    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [
                {
                    "id": "stop_area:dep",
                    "name": "Paris Gare de Lyon",
                }
            ],
            None,
        ]
    )

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.subentries.flow.async_init(
            (entry.entry_id, "train"),
            context={"source": config_entries.SOURCE_USER},
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_CITY: "Paris",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_STATION: "stop_area:dep",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ARRIVAL_CITY: "Lyon",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "arrival_city"
    assert result["errors"]["base"] == "no_stations"


@pytest.mark.asyncio
async def test_train_subentry_duplicate(hass):
    """Test that an identical train subentry cannot be created twice."""
    existing_subentry = {
        "data": {
            "from": "stop_area:dep",
            "to": "stop_area:arr",
            "departure_name": "Paris Gare de Lyon",
            "arrival_name": "Lyon Part Dieu",
            "time_start": "07:00",
            "time_end": "10:00",
            "train_count": 5,
        },
        "subentry_type": "train",
        "title": "Existing train",
        "unique_id": "stop_area:dep_stop_area:arr_07:00_10:00",
    }

    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "valid_key"},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
        subentries_data=(existing_subentry,),
    )
    entry.add_to_hass(hass)

    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [
                {
                    "id": "stop_area:dep",
                    "name": "Paris Gare de Lyon",
                }
            ],
            [
                {
                    "id": "stop_area:arr",
                    "name": "Lyon Part Dieu",
                }
            ],
        ]
    )

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient",
        return_value=mock_api,
    ):
        result = await hass.config_entries.subentries.flow.async_init(
            (entry.entry_id, "train"),
            context={"source": config_entries.SOURCE_USER},
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_CITY: "Paris",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEPARTURE_STATION: "stop_area:dep",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ARRIVAL_CITY: "Lyon",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_ARRIVAL_STATION: "stop_area:arr",
            },
        )

        result = await hass.config_entries.subentries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_TIME_START: "07:00",
                CONF_TIME_END: "10:00",
                CONF_TRAIN_COUNT: 5,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured_as_entry"


@pytest.mark.asyncio
async def test_options_flow(hass):
    """Test the integration options flow."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Trains SNCF",
        data={CONF_API_KEY: "valid_key"},
        options={},
        source=config_entries.SOURCE_USER,
        unique_id="sncf_trains",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "update_interval": 5,
            "outside_interval": 30,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "update_interval": 5,
        "outside_interval": 30,
    }
