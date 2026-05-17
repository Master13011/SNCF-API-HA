"""Data Update Coordinator for SNCF integration."""

import logging
from datetime import timedelta
from typing import Any
import asyncio
from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
        """Initialisation du coordinateur."""
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
        """Paramétrage du client API au démarrage."""
        api_key = self.entry.data[CONF_API_KEY]

        try:
            session = async_get_clientsession(self.hass)
            self.api_client = SncfApiClient(session, api_key)
        except Exception as err:
            _LOGGER.error("Erreur d'initialisation API SNCF: %s", err)
            raise UpdateFailed(err) from err

    def _build_datetime_param(self, time_start: str, time_end: str) -> str:
        """Construit le paramètre datetime pour l'API en ignorant le passé."""
        now = dt_util.now()
        h_start, m_start = map(int, time_start.split(":"))
        h_end, m_end = map(int, time_end.split(":"))
        
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        if now > dt_end:
            dt_start += timedelta(days=1)
        elif now > dt_start:
            dt_start = now

        return dt_start.strftime("%Y%m%dT%H%M%S")

    def _adjust_update_interval(self, time_start: str, time_end: str) -> timedelta:
        """Calcule l'intervalle approprié (Actif vs Éco)."""
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
        return timedelta(minutes=interval_minutes)

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère les données depuis l'API SNCF."""
        if not self.entry.subentries:
            return {}

        update_intervals = []
        trains = {}
        max_retries = 3
        retry_delay = 2

        for subentry_id, entry in self.entry.subentries.items():
            departure = entry.data[CONF_FROM]
            arrival = entry.data[CONF_TO]
            time_start = entry.data[CONF_TIME_START]
            time_end = entry.data[CONF_TIME_END]
            train_count = entry.data.get("train_count", 10)

            update_intervals.append(self._adjust_update_interval(time_start, time_end))
            datetime_str = self._build_datetime_param(time_start, time_end)
            
            journeys_data = None
            for attempt in range(1, max_retries + 1):
                try:
                    journeys_data = await self.api_client.fetch_journeys(
                        departure, arrival, datetime_str, count=train_count
                    )
                    if journeys_data is not None:
                        break
                except (ClientError, asyncio.TimeoutError, RuntimeError) as err:
                    _LOGGER.warning("Tentative %d/%d échouée: %s", attempt, max_retries, err)
                await asyncio.sleep(retry_delay)

            # Vérification du dictionnaire
            if journeys_data is None or not isinstance(journeys_data, dict):
                continue

            # Extraction séparée
            journeys_list = journeys_data.get("journeys", [])
            disruptions_list = journeys_data.get("disruptions", [])

            valid_journeys = []
            for j in journeys_list:
                if isinstance(j, dict) and len(j.get("sections", [])) == 1:
                    # 👈 LA MAGIE : On injecte les perturbations dans chaque trajet
                    j["_disruptions"] = disruptions_list
                    valid_journeys.append(j)

            trains[subentry_id] = valid_journeys

        if update_intervals:
            new_interval = min(update_intervals)
            if self.update_interval != new_interval:
                self.update_interval = new_interval
                _LOGGER.debug("Nouvel intervalle de mise à jour: %s min", new_interval.total_seconds() / 60)

        return trains