from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SncfApiClient
from .const import (
    CONF_API_KEY,
    CONF_ARRIVAL_CITY,
    CONF_ARRIVAL_NAME,
    CONF_ARRIVAL_STATION,
    CONF_DEPARTURE_CITY,
    CONF_DEPARTURE_NAME,
    CONF_DEPARTURE_STATION,
    CONF_FROM,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_TRAIN_COUNT,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_TRAIN_COUNT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


class SncfTrainsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = SncfApiClient(session, user_input[CONF_API_KEY])
            if not await self._validate_api_key(api):
                errors["base"] = "invalid_api_key"
            else:
                if self.source == "user":
                    await self.async_set_unique_id("sncf_trains")
                    return self.async_create_entry(title="Trains SNCF", data=user_input)
                else:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(), data=user_input
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def _validate_api_key(self, api: SncfApiClient):
        try:
            results = await api.search_stations("paris")
            return bool(results)
        except Exception:
            return False

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "train": TrainSubentryFlowHandler,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return SncfTrainsOptionsFlowHandler()

    async_step_reconfigure = async_step_user


class SncfTrainsOptionsFlowHandler(OptionsFlow):
    """Options flow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required("update_interval", default=DEFAULT_UPDATE_INTERVAL): int,
                vol.Required("outside_interval", default=DEFAULT_OUTSIDE_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=DATA_SCHEMA)


class TrainSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing trains subentries."""

    api: SncfApiClient | None = None
    departure_city: str | None = None
    departure_station: str | None = None
    arrival_city: str | None = None
    arrival_station: str | None = None
    departure_options: dict = {}
    arrival_options: dict = {}
    config_entry: ConfigEntry | None = None

    async def async_step_departure_city(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors = {}
        if user_input is not None:
            self.config_entry = self._get_entry()
            api_key = self.config_entry.options.get(
                "api_key"
            ) or self.config_entry.data.get("api_key")
            session = async_get_clientsession(self.hass)
            self.api = SncfApiClient(session, api_key)

            self.departure_city = user_input[CONF_DEPARTURE_CITY]
            stations = await self.api.search_stations(self.departure_city)
            if not stations:
                errors["base"] = "no_stations"
            else:
                self.departure_options = {s["id"]: s for s in stations}
                return await self.async_step_departure_station()
        return self.async_show_form(
            step_id="departure_city",
            data_schema=vol.Schema({vol.Required(CONF_DEPARTURE_CITY): str}),
            errors=errors,
        )

    async def async_step_departure_station(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self.departure_station = user_input[CONF_DEPARTURE_STATION]
            return await self.async_step_arrival_city()
        options = {
            k: f"{v['name']} ({k.split(':')[-1]})"
            for k, v in self.departure_options.items()
        }
        return self.async_show_form(
            step_id="departure_station",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEPARTURE_STATION): vol.In(options)}
            ),
        )

    async def async_step_arrival_city(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors = {}
        if user_input is not None:
            self.arrival_city = user_input[CONF_ARRIVAL_CITY]
            stations = await self.api.search_stations(self.arrival_city)
            if not stations:
                errors["base"] = "no_stations"
            else:
                self.arrival_options = {s["id"]: s for s in stations}
                return await self.async_step_arrival_station()
        return self.async_show_form(
            step_id="arrival_city",
            data_schema=vol.Schema({vol.Required(CONF_ARRIVAL_CITY): str}),
            errors=errors,
        )

    async def async_step_arrival_station(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self.arrival_station = user_input[CONF_ARRIVAL_STATION]
            return await self.async_step_time_range()
        options = {
            k: f"{v['name']} ({k.split(':')[-1]})"
            for k, v in self.arrival_options.items()
        }
        return self.async_show_form(
            step_id="arrival_station",
            data_schema=vol.Schema(
                {vol.Required(CONF_ARRIVAL_STATION): vol.In(options)}
            ),
        )

    async def async_step_time_range(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            dep_name = self.departure_options.get(self.departure_station, {}).get(
                "name", self.departure_station
            )
            arr_name = self.arrival_options.get(self.arrival_station, {}).get(
                "name", self.arrival_station
            )
            time_start = user_input[CONF_TIME_START]
            time_end = user_input[CONF_TIME_END]
            unique_id = f"{self.departure_station}_{self.arrival_station}_{time_start}_{time_end}"

            for subentry in self.config_entry.subentries.values():
                if unique_id == subentry.unique_id:
                    return self.async_abort(reason="already_configured_as_entry")

            return self.async_create_entry(
                title=f"Trajet: {dep_name} → {arr_name} ({time_start} - {time_end})",
                data={
                    CONF_FROM: self.departure_station,
                    CONF_TO: self.arrival_station,
                    CONF_DEPARTURE_NAME: dep_name,
                    CONF_ARRIVAL_NAME: arr_name,
                    **user_input,
                },
                unique_id=unique_id,
            )
        return self.async_show_form(
            step_id="time_range",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TIME_START, default=DEFAULT_TIME_START): str,
                    vol.Required(CONF_TIME_END, default=DEFAULT_TIME_END): str,
                    vol.Required(CONF_TRAIN_COUNT, default=DEFAULT_TRAIN_COUNT): int,
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to modify an existing location."""
        config_subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            data = config_subentry.data.copy()
            data.update(user_input)

            return self.async_update_and_abort(
                self._get_entry(), config_subentry, data=data
            )

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_TIME_START, default=DEFAULT_TIME_START): str,
                vol.Required(CONF_TIME_END, default=DEFAULT_TIME_END): str,
                vol.Required(CONF_TRAIN_COUNT, default=DEFAULT_TRAIN_COUNT): int,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA, config_subentry.data
            ),
        )

    async_step_user = async_step_departure_city
