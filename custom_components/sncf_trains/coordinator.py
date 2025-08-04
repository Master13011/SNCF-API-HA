import logging
from datetime import timedelta
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DEFAULT_UPDATE_INTERVAL
from datetime import timedelta as dt_timedelta

_LOGGER = logging.getLogger(__name__)

class SncfUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api_client, departure, arrival, time_start, time_end, update_interval=None):
        self.api_client = api_client
        self.departure = departure
        self.arrival = arrival
        self.time_start = time_start
        self.time_end = time_end
        # Convert update_interval (int, minutes) en timedelta, fallback à DEFAULT_UPDATE_INTERVAL (minutes)
        interval_min = update_interval if update_interval is not None else DEFAULT_UPDATE_INTERVAL
        update_interval_td = dt_timedelta(minutes=interval_min)

        super().__init__(
            hass,
            _LOGGER,
            name=f"SNCF Train Journeys {departure}→{arrival}",
            update_interval=update_interval_td,
        )

    def _build_datetime_param(self) -> str:
        now = dt_util.now()
        h_start, m_start = map(int, self.time_start.split(":"))
        h_end, m_end = map(int, self.time_end.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)
        if now > dt_end:
            dt_start += timedelta(days=1)
        return dt_start.strftime("%Y%m%dT%H%M%S")

    async def _async_update_data(self):
        datetime_str = self._build_datetime_param()
        try:
            journeys = await self.api_client.fetch_journeys(
                self.departure, self.arrival, datetime_str, count=10
            )
        except Exception as err:
            _LOGGER.error("Erreur lors de la récupération des trajets SNCF: %s", err)
            raise UpdateFailed(err)
        if journeys is None:
            raise UpdateFailed("Aucune donnée reçue de l'API SNCF")
        return journeys

