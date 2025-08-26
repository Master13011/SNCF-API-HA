import pytest
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from custom_components.sncf_trains.const import DOMAIN, CONF_API_KEY


@pytest.mark.asyncio
async def test_config_flow_happy_path(hass):
    """Test config flow with valid API key and stations."""
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(
        side_effect=[
            [{"id": "stop_area:dep", "name": "Paris Gare de Lyon"}],  # departure city
            [{"id": "stop_area:arr", "name": "Lyon Part Dieu"}],       # arrival city
        ]
    )

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient", return_value=mock_api
    ):
        # Step 1: saisie API key
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "valid_key"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "departure_city"

        # Step 2: ville départ
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"departure_city": "Paris"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "departure_station"

        # Step 3: station départ
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"departure_station": "stop_area:dep"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "arrival_city"

        # Step 4: ville arrivée
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"arrival_city": "Lyon"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "arrival_station"

        # Step 5: station arrivée
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"arrival_station": "stop_area:arr"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "time_range"

        # Step 6: plage horaire + finalisation
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"time_start": "07:00", "time_end": "10:00"}
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "SNCF: Paris Gare de Lyon → Lyon Part Dieu"
        assert result["data"]["departure_name"] == "Paris Gare de Lyon"


@pytest.mark.asyncio
async def test_config_flow_invalid_api_key(hass):
    """Test config flow with invalid API key."""
    mock_api = AsyncMock()
    mock_api.search_stations = AsyncMock(return_value=None)

    with patch(
        "custom_components.sncf_trains.config_flow.SncfApiClient", return_value=mock_api
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "bad_key"}
        )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_api_key"

