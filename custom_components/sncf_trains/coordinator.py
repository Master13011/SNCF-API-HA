import logging
from datetime import timedelta
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DEFAULT_UPDATE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed

_LOGGER = logging.getLogger(__name__)


class SncfUpdateCoordinator(DataUpdateCoordinator):
    """Coordonnateur pour récupérer les données des trajets SNCF."""

    def __init__(
        self,
        hass,
        api_client,
        departure,
        arrival,
        time_start,
        time_end,
        update_interval=None,
        outside_interval=None,
        config_entry=None,
    ):
        self.api_client = api_client
        self.departure = departure
        self.arrival = arrival
        self.time_start = time_start
        self.time_end = time_end
        self.config_entry = config_entry

        # Intervalles par défaut (en minutes)
        self.update_interval_minutes = (
            update_interval if update_interval is not None else DEFAULT_UPDATE_INTERVAL
        )
        self.outside_interval_minutes = (
            outside_interval if outside_interval is not None else DEFAULT_OUTSIDE_INTERVAL
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"SNCF Train Journeys {departure}→{arrival}",
            update_interval=timedelta(minutes=self.update_interval_minutes),
        )

    def _build_datetime_param(self) -> str:
        """Construit le paramètre datetime pour l'API."""
        now = dt_util.now()
        h_start, m_start = map(int, self.time_start.split(":"))
        h_end, m_end = map(int, self.time_end.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        # Si on est après la fin, on décale le début au lendemain
        if now > dt_end:
            dt_start += timedelta(days=1)

        return dt_start.strftime("%Y%m%dT%H%M%S")

    def _adjust_update_interval(self):
        """Ajuste la fréquence de mise à jour selon la plage horaire."""
        now = dt_util.now().time()
        h_start, m_start = map(int, self.time_start.split(":"))
        h_end, m_end = map(int, self.time_end.split(":"))
        start_time = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        end_time = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        # Heures de pointe
        if start_time <= now <= end_time:
            interval_minutes = self.update_interval_minutes
        else:
            interval_minutes = self.outside_interval_minutes

        # Appliquer le nouvel intervalle
        new_interval = timedelta(minutes=interval_minutes)
        if self.update_interval != new_interval:
            _LOGGER.debug(
                "Changement d'intervalle de mise à jour: %s → %s minutes",
                self.update_interval.total_seconds() / 60,
                interval_minutes,
            )
            self.update_interval = new_interval

    async def _async_update_data(self):
        """Récupère les données de l'API SNCF."""
        # Adapter la fréquence de mise à jour
        self._adjust_update_interval()

        datetime_str = self._build_datetime_param()
        try:
            journeys = await self.api_client.fetch_journeys(
                self.departure,
                self.arrival,
                datetime_str,
                count=10,
            )
        except Exception as err:
            # Si c'est une erreur d'authentification
            if "401" in str(err) or "403" in str(err):
                raise ConfigEntryAuthFailed("Clé API invalide ou expirée") from err
            _LOGGER.error("Erreur lors de la récupération des trajets SNCF: %s", err)
            raise UpdateFailed(err)

        if journeys is None:
            raise UpdateFailed("Aucune donnée reçue de l'API SNCF")

        return journeys
