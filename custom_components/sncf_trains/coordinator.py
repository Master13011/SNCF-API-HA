"""Data Update Coordinator."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .helpers import format_time, get_duration, get_train_num, parse_datetime
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
            CONF_UPDATE_INTERVAL,
            DEFAULT_UPDATE_INTERVAL,
        )

        self.outside_interval_minutes = entry.options.get(
            CONF_OUTSIDE_INTERVAL,
            DEFAULT_OUTSIDE_INTERVAL,
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

            _LOGGER.error(
                "Erreur lors de la récupération des trajets SNCF: %s",
                err,
            )
            raise UpdateFailed(err) from err

    def _build_datetime_param(self, time_start, time_end) -> str:
        """Construit le paramètre datetime pour l'API."""
        now = dt_util.now()

        h_start, m_start = map(int, time_start.split(":"))
        h_end, m_end = map(int, time_end.split(":"))

        dt_start = now.replace(
            hour=h_start,
            minute=m_start,
            second=0,
            microsecond=0,
        )

        dt_end = now.replace(
            hour=h_end,
            minute=m_end,
            second=0,
            microsecond=0,
        )

        if now > dt_end:
            dt_start += timedelta(days=1)

        return dt_start.strftime("%Y%m%dT%H%M%S")

    def _adjust_update_interval(
        self,
        time_start,
        time_end,
    ) -> timedelta | None:
        """Ajuste la fréquence selon la plage horaire."""
        now = dt_util.now()

        h_start, m_start = map(int, time_start.split(":"))
        h_end, m_end = map(int, time_end.split(":"))

        start = now.replace(
            hour=h_start,
            minute=m_start,
            second=0,
            microsecond=0,
        )

        end = now.replace(
            hour=h_end,
            minute=m_end,
            second=0,
            microsecond=0,
        )

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
                (
                    None
                    if self.update_interval is None
                    else self.update_interval.total_seconds() / 60
                ),
                interval_minutes,
            )

        return new_interval

    @staticmethod
    def _train_number(value: Any) -> str:
        """Normalize train numbers without changing their significant digits."""
        return "".join(str(value or "").split()).lstrip("0") or "0"

    @staticmethod
    def _matching_departure(journey: dict, item: dict, station_uic: str) -> bool:
        """Match a train at the selected boarding station and on the same day."""
        from datetime import datetime

        sections = journey.get("sections") or []
        section = next(
            (s for s in sections if isinstance(s, dict)
             and s.get("type") == "public_transport"),
            {},
        )
        scheduled = section.get("base_departure_date_time") or journey.get(
            "departure_date_time"
        )
        stop = next(
            (s for s in (item.get("JourneyStop") or [])
             if isinstance(s, dict) and s.get("uic") == station_uic),
            None,
        )
        gc_time = (stop or item).get("scheduledTime")
        try:
            nav_time = parse_datetime(scheduled)
            gc_dt = datetime.fromisoformat(gc_time.replace("Z", "+00:00"))
            if nav_time is None or gc_dt.tzinfo is None:
                return False
            return abs((nav_time - gc_dt).total_seconds()) <= 20 * 60
        except (TypeError, ValueError, AttributeError):
            return False

    async def _enrich_journeys(self, journeys: list[dict], station_uic: str) -> None:
        """Fetch boarding platforms and, where available, train compositions."""
        session = async_get_clientsession(self.hass)
        url = (
            "https://www.garesetconnexions.sncf/schedule-table/"
            f"Departures/{station_uic}"
        )
        async with session.get(url, timeout=8) as response:
            if response.status != 200:
                _LOGGER.debug("G&C timetable HTTP %s", response.status)
                return
            timetable = await response.json(content_type=None)
        if not isinstance(timetable, list):
            return

        # A train may pass this station after starting at an earlier station.
        by_number: dict[str, list[dict]] = {}
        for item in timetable:
            if isinstance(item, dict):
                by_number.setdefault(
                    self._train_number(item.get("trainNumber")), []
                ).append(item)

        # Reuse course results for repeated journeys within the same refresh.
        details_cache: dict[tuple[str, str], dict | None] = {}
        for journey in journeys:
            number = self._train_number(get_train_num(journey))
            candidates = by_number.get(number, [])
            if not candidates:
                continue

            # Timetable items may omit JourneyStop; fetch details before matching.
            for item in candidates:
                circulation_id = item.get("circulationId")
                if not isinstance(circulation_id, str) or not circulation_id:
                    if self._matching_departure(journey, item, station_uic):
                        platform = item.get("platform") or {}
                        if isinstance(platform, dict) and platform.get("track"):
                            journey["platform_track"] = str(platform["track"])
                        break
                    continue
                key = (station_uic, circulation_id)
                if key not in details_cache:
                    course_url = (
                        "https://live-portal-back.azurewebsites.net/api/course/"
                        f"{station_uic.lstrip('0')}/{circulation_id}"
                    )
                    try:
                        async with session.get(
                            course_url,
                            params={"isDeparture": "true"},
                            headers={"x-environment": "PROD",
                                     "Origin": "https://green-pebble-049918603.7.azurestaticapps.net"},
                            timeout=8,
                        ) as response:
                            if response.status == 200:
                                payload = await response.json(content_type=None)
                                details_cache[key] = (
                                    payload[0] if isinstance(payload, list)
                                    and payload and isinstance(payload[0], dict)
                                    else None
                                )
                            else:
                                details_cache[key] = None
                    except (ClientError, asyncio.TimeoutError, ValueError) as err:
                        _LOGGER.debug("G&C course unavailable: %s", err)
                        details_cache[key] = None

                detail = details_cache[key]
                match_source = detail if detail else item
                if not self._matching_departure(journey, match_source, station_uic):
                    continue

                stop = next(
                    (s for s in (match_source.get("JourneyStop") or [])
                     if isinstance(s, dict) and s.get("uic") == station_uic),
                    None,
                )
                platform = (stop or match_source).get("platform") or {}
                if isinstance(platform, dict) and platform.get("track"):
                    journey["platform_track"] = str(platform["track"])

                if detail:
                    composition = detail.get("composition") or {}
                    elements = composition.get("element") if isinstance(
                        composition, dict
                    ) else None
                    if isinstance(elements, list):
                        units = [
                            str(e["numeroAffectation"])
                            for e in elements
                            if isinstance(e, dict) and e.get("numeroAffectation")
                        ]
                        journey["train_units"] = len(elements)
                        journey["train_composition"] = units
                        # Known Z 24500 vehicles are TER 2N NG (three cars).
                        # Only label the family when every identified unit matches.
                        import re

                        if units and len(units) == len(elements) and all(
                            re.search(r"Z\\s*24[5-7]\\d{2}$", unit, re.IGNORECASE)
                            for unit in units
                        ):
                            journey["train_family"] = "Z 24500"
                            journey["train_type"] = "TER 2N NG"
                            journey["train_cars"] = 3 * len(units)

                    journey["train_length"] = detail.get("trainLength")
                break

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère les données de l'API SNCF."""

        if not self.entry.subentries:
            _LOGGER.warning("Pas de subentries configurés")
            return {}

        update_intervals = []
        trains = {}

        max_retries = 3
        retry_delay = 2

        for subentry_id, entry in self.entry.subentries.items():
            _LOGGER.debug(
                "Traitement du trajet : %s",
                entry.title,
            )

            departure = entry.data[CONF_FROM]
            arrival = entry.data[CONF_TO]
            time_start = entry.data[CONF_TIME_START]
            time_end = entry.data[CONF_TIME_END]

            update_intervals.append(
                self._adjust_update_interval(
                    time_start,
                    time_end,
                )
            )

            datetime_str = self._build_datetime_param(
                time_start,
                time_end,
            )

            journeys = None

            # ---------------------------------------------------------
            # Appel API avec retry
            # ---------------------------------------------------------
            for attempt in range(1, max_retries + 1):
                try:
                    journeys = await self.api_client.fetch_journeys(
                        departure,
                        arrival,
                        datetime_str,
                        count=10,
                    )

                    if journeys is not None:
                        break

                except (
                    ClientError,
                    asyncio.TimeoutError,
                    RuntimeError,
                ) as err:
                    _LOGGER.warning(
                        "Erreur réseau lors de la récupération des trajets "
                        "(tentative %d/%d) : %s",
                        attempt,
                        max_retries,
                        err,
                    )

                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)

            # ---------------------------------------------------------
            # Vérification de la réponse API
            # ---------------------------------------------------------
            if journeys is None or not isinstance(journeys, list):
                _LOGGER.error(
                    "Aucune donnée reçue de l'API SNCF pour le trajet '%s'",
                    entry.title,
                )
                continue

            _LOGGER.debug(
                "Trajet '%s' : %d journey(s) reçu(s) depuis l'API",
                entry.title,
                len(journeys),
            )

            # ---------------------------------------------------------
            # Filtrage des trajets
            #
            # On ne teste plus le nombre de sections.
            #
            # Un trajet direct peut maintenant être représenté par :
            #
            #   crow_fly
            #   public_transport
            #   crow_fly
            #
            # tout en ayant nb_transfers = 0.
            #
            # nb_transfers est donc le critère approprié pour
            # éliminer les trajets avec correspondance.
            # ---------------------------------------------------------
            filtered_journeys = []

            for journey in journeys:
                if not isinstance(journey, dict):
                    continue

                if journey.get("nb_transfers", 0) == 0:
                    filtered_journeys.append(journey)

            _LOGGER.debug(
                "Trajet '%s' : %d journey(s) conservé(s) après filtrage "
                "(sans correspondance)",
                entry.title,
                len(filtered_journeys),
            )

            # Gares & Connexions: timetable plus optional circulation details.
            # Keep SNCF/Navitia journeys usable when this unofficial API fails.
            station_uic = departure.split(":")[-1]
            if station_uic.isdigit() and filtered_journeys:
                try:
                    await self._enrich_journeys(
                        filtered_journeys, station_uic.zfill(10)
                    )
                except Exception as err:
                    _LOGGER.debug("Gares & Connexions enrichment failed: %s", err)

            trains[subentry_id] = filtered_journeys

        # -------------------------------------------------------------
        # Mise à jour de l'intervalle
        # -------------------------------------------------------------
        if update_intervals:
            new_interval = min(update_intervals)

            if self.update_interval != new_interval:
                self.update_interval = new_interval

                _LOGGER.debug(
                    "Coordinator update interval set to %s minutes",
                    self.update_interval.total_seconds() / 60,
                )

        return trains
