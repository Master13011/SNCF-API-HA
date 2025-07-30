import logging
from datetime import timedelta, datetime
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from .api import fetch_journeys
from .const import CONF_API_KEY, CONF_FROM, CONF_TO, CONF_TIME_START, CONF_TIME_END, DEFAULT_UPDATE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class SncfDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry):
        self.hass = hass
        self.api_key = entry.data[CONF_API_KEY]
        self.from_station = entry.data[CONF_FROM]
        self.to_station = entry.data[CONF_TO]
        self.time_start = entry.data.get(CONF_TIME_START, "07:00")
        self.time_end = entry.data.get(CONF_TIME_END, "10:00")


        update_interval = int(entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL))
        outside_interval = int(entry.options.get("outside_interval", DEFAULT_OUTSIDE_INTERVAL))


        super().__init__(
            hass,
            _LOGGER,
            name="SNCF Coordinator",
            update_interval=timedelta(minutes=update_interval),
        )
        self.outside_interval = timedelta(minutes=outside_interval)

    def _build_datetime_param(self):
        now = datetime.now()
        h_start, m_start = map(int, self.time_start.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        if now > dt_start:
            dt_start += timedelta(days=1)
        return dt_start.strftime("%Y%m%dT%H%M%S")

    async def _async_update_data(self):
        try:
            return await fetch_journeys(
                api_key=self.api_key,
                from_id=self.from_station,
                to_id=self.to_station,
                datetime_str=self._build_datetime_param()
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}")
