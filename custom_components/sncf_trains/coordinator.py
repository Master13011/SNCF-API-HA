"""Data Update Coordinator."""

import logging
from datetime import timedelta
from itertools import count
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SncfApiClient
from .const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_OUTSIDE_INTERVAL,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SncfUpdateCoordinator(DataUpdateCoordinator):
    """Coordonnateur pour récupérer les données des trajets SNCF."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialisation."""
        self.entry = entry
        self.api_client = None
        self.update_interval_minutes = entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        self.outside_interval_minutes = entry.options.get(
            CONF_OUTSIDE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL
        )

        super().__init__(
            hass,
            _LOGGER,
            name="SNCF Train Journeys",
            update_interval=timedelta(minutes=self.update_interval_minutes),
        )

    async def _async_setup(self) -> None:
        """Paramétrage du coordinateur."""
        api_key = self.entry.data[CONF_API_KEY]

        try:
            session = async_get_clientsession(self.hass)
            self.api_client = SncfApiClient(session, api_key)

        except Exception as err:
            if "401" in str(err) or "403" in str(err):
                raise ConfigEntryAuthFailed("Clé API invalide ou expirée") from err
            _LOGGER.error("Erreur lors de la récupération des trajets SNCF: %s", err)
            raise UpdateFailed(err)

    def _build_datetime_param(self, time_start, time_end) -> str:
        """Construit le paramètre datetime pour l'API."""
        now = dt_util.now()
        h_start, m_start = map(int, time_start.split(":"))
        h_end, m_end = map(int, time_end.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        if now > dt_end:
            dt_start += timedelta(days=1)

        return dt_start.strftime("%Y%m%dT%H%M%S")

    def _adjust_update_interval(self, time_start, time_end) -> timedelta | None:
        """Ajuste la fréquence selon la plage horaire, avec préfenêtre 1h et gestion minuit."""
        now = dt_util.now()
        h_start, m_start = map(int, time_start.split(":"))
        h_end, m_end = map(int, time_end.split(":"))

        start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        if end <= start:
            end += timedelta(days=1)

        pre_start = start - timedelta(hours=1)

        if now < pre_start:
            start -= timedelta(days=1)
            end -= timedelta(days=1)
            pre_start -= timedelta(days=1)

        in_fast_mode = pre_start <= now <= end

        interval_minutes = (
            self.update_interval_minutes
            if in_fast_mode
            else self.outside_interval_minutes
        )
        new_interval = timedelta(minutes=interval_minutes)

        if self.update_interval != new_interval:
            _LOGGER.debug(
                "Update interval: %s → %s minutes",
                None
                if self.update_interval is None
                else self.update_interval.total_seconds() / 60,
                interval_minutes,
            )
            return new_interval

        return new_interval

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère les données de l'API SNCF."""

        update_intervals = []
        trains = {}
        for id, entry in self.entry.subentries.items():
            _LOGGER.debug(entry.title)
            departure = entry.data[CONF_FROM]
            arrival = entry.data[CONF_TO]
            time_start = entry.data[CONF_TIME_START]
            time_end = entry.data[CONF_TIME_END]

            update_intervals.append(self._adjust_update_interval(time_start, time_end))
            datetime_str = self._build_datetime_param(time_start, time_end)

            try:
                journeys = await self.api_client.fetch_journeys(
                    departure, arrival, datetime_str, count=10
                )
            except Exception as err:
                _LOGGER.error(
                    "Erreur lors de la récupération des trajets SNCF: %s", err
                )
                raise UpdateFailed(err)

            if journeys is None or not isinstance(journeys, list):
                _LOGGER.error("Aucune donnée reçue de l'API SNCF pour le trajet ")
                continue

            i = count(0)
            trains.update(
                {
                    id: [
                        j
                        for j in journeys
                        if isinstance(j, dict) and len(j.get("sections", [])) == 1
                    ]
                }
            )

        self.update_interval = min(update_intervals)
        _LOGGER.debug(
            "Coordinator update interval: %s minutes",
            self.update_interval.total_seconds() / 60,
        )

        return trains
