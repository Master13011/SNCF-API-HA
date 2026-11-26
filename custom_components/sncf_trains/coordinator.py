"""Data Update Coordinator."""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .helpers import (
    disruption_summary,
    format_time,
    get_duration,
    get_stop_uic,
    get_train_num,
    parse_datetime,
    parse_hhmm,
    stop_identifiers,
)
from .rolling_stock import analyser_composition
from .api import SncfApiClient
from .const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_DEPARTURE_NAME,
    CONF_ARRIVAL_NAME,
    CONF_OUTSIDE_INTERVAL,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# Après un échec complet du repli (horaires théoriques + résolution des IDs),
# on ne retente pas avant ce délai afin de ne pas consommer le quota de l'API.
FALLBACK_RETRY_SECONDS = 30 * 60


class SncfUpdateCoordinator(DataUpdateCoordinator):
    """Coordonnateur pour récupérer les données des trajets SNCF."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialisation."""
        self.entry = entry
        self.api_client = None
        # IDs NeTEx may differ from the legacy Navitia IDs. Cache resolved IDs
        # for this coordinator lifetime; persisted station names remain stable.
        self._netex_station_ids: dict[tuple[str, str], tuple[str, str]] = {}
        # subentry_id -> instant (time.monotonic) avant lequel le repli est suspendu
        self._fallback_retry_at: dict[str, float] = {}
        # stop_id -> UIC (ou None) résolu via l'API quand la réponse du trajet
        # n'embarque pas les ``codes`` de l'arrêt (gares frontalières).
        self._uic_cache: dict[str, str | None] = {}
        self._uic_warned: set[str] = set()
        self._circulation_cache: dict[tuple, dict] = {}

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
            config_entry=entry,
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

        await self._async_backfill_station_names()

    @staticmethod
    def _needs_station_name(name: Any, station_id: str) -> bool:
        """Indique si le nom enregistré est absent ou n'est qu'un identifiant."""
        if not isinstance(name, str) or not name.strip():
            return True
        return name == station_id or name.startswith(
            ("stop_area:", "stop_point:", "admin:")
        )

    async def _async_backfill_station_names(self) -> None:
        """Complète les noms de gares manquants des trajets déjà configurés.

        Les trajets migrés depuis d'anciennes versions peuvent n'avoir que des
        identifiants, ce qui empêche de retrouver les nouveaux IDs NeTEx.
        Tant que les anciens IDs sont reconnus par l'API, on récupère le nom
        et on le sauvegarde dans la sous-entrée. Meilleur effort : toute erreur
        est ignorée et sera retentée au prochain démarrage.
        """
        if self.api_client is None:
            return

        for subentry in self.entry.subentries.values():
            data = dict(subentry.data)
            changes: dict[str, str] = {}
            for id_key, name_key in (
                (CONF_FROM, CONF_DEPARTURE_NAME),
                (CONF_TO, CONF_ARRIVAL_NAME),
            ):
                station_id = data.get(id_key)
                if not isinstance(station_id, str):
                    continue
                if not self._needs_station_name(data.get(name_key), station_id):
                    continue
                try:
                    name = await self.api_client.fetch_station_name(station_id)
                except ConfigEntryAuthFailed:
                    raise
                except Exception as err:  # noqa: BLE001 - meilleur effort
                    _LOGGER.debug(
                        "Nom de gare introuvable pour %s : %s", station_id, err
                    )
                    continue
                if name:
                    changes[name_key] = name

            if changes:
                try:
                    self.hass.config_entries.async_update_subentry(
                        self.entry, subentry, data={**data, **changes}
                    )
                    _LOGGER.info(
                        "Noms de gares enregistrés pour '%s' : %s",
                        subentry.title,
                        changes,
                    )
                except Exception as err:  # noqa: BLE001 - meilleur effort
                    _LOGGER.warning(
                        "Impossible d'enregistrer les noms de gares : %s", err
                    )

    def _build_datetime_param(self, time_start, time_end) -> str:
        """Construit le paramètre datetime pour l'API."""
        now = dt_util.now()

        h_start, m_start = parse_hhmm(time_start)
        h_end, m_end = parse_hhmm(time_end)

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

        h_start, m_start = parse_hhmm(time_start)
        h_end, m_end = parse_hhmm(time_end)

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


    async def _async_stop_uic(self, place: Any) -> str | None:
        """Return the UIC (8 digits) of a section ``from``/``to`` place.

        1. ``codes`` embedded in the journey response (new NeTEx referential);
        2. legacy IDs carrying the UIC;
        3. lookup of the stop through the API (cached).
        """
        uic = get_stop_uic(place)
        if uic:
            return uic
        if self.api_client is None:
            return None
        for identifier in stop_identifiers(place):
            if not identifier.startswith(("stop_point:", "stop_area:")):
                continue
            if identifier not in self._uic_cache:
                try:
                    self._uic_cache[identifier] = await self.api_client.fetch_stop_uic(
                        identifier
                    )
                except ConfigEntryAuthFailed:
                    raise
                except Exception as err:  # noqa: BLE001 - meilleur effort
                    _LOGGER.debug("UIC lookup failed for %s: %s", identifier, err)
                    self._uic_cache[identifier] = None
            if self._uic_cache[identifier]:
                return self._uic_cache[identifier]
        # Une seule alerte par gare, pour pouvoir l'ajouter à la table de repli
        # (_UIC_FALLBACK_BY_NETEX dans helpers.py).
        key = next(iter(stop_identifiers(place)), None)
        if key and key not in self._uic_warned:
            self._uic_warned.add(key)
            _LOGGER.warning(
                "Aucun UIC pour la gare '%s' (id=%s) : quai et composition "
                "indisponibles. UIC connu ? Ajoutez-le dans "
                "_UIC_FALLBACK_BY_NETEX (helpers.py).",
                (place or {}).get("name") if isinstance(place, dict) else None,
                key,
            )
        return None

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
             if isinstance(s, dict) and str(s.get("uic", "")).zfill(10) == station_uic),
            None,
        )
        gc_time = (stop or item).get("scheduledTime")
        try:
            nav_time = parse_datetime(scheduled)
            gc_dt = datetime.fromisoformat(gc_time.replace("Z", "+00:00"))
            if nav_time is None:
                return False
            if gc_dt.tzinfo is None:
                gc_dt = gc_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            return abs((nav_time - gc_dt).total_seconds()) <= 20 * 60
        except (TypeError, ValueError, AttributeError):
            return False

    def _circulation_key(self, journey: dict, station_uic: str) -> tuple | None:
        section = next(
            (s for s in journey.get("sections", []) if isinstance(s, dict)
             and s.get("type") == "public_transport"), {},
        )
        scheduled = parse_datetime(section.get("base_departure_date_time"))
        number = get_train_num(journey)
        arrival = journey.get("arrival_uic") or get_stop_uic(section.get("to"))
        if not (scheduled and number and arrival):
            return None
        return (self._train_number(number), station_uic, str(arrival).zfill(10), scheduled.isoformat())

    @staticmethod
    def _cancelled(journey: dict) -> bool:
        return str(journey.get("status", "")).upper() in {
            "NO_SERVICE", "CANCELLED", "CANCELED"
        } or disruption_summary(journey)["disruption_effect"] == "NO_SERVICE"

    @staticmethod
    def _gc_live_status(*sources: Any) -> dict[str, Any]:
        """Lit retard / suppression dans les données Gares & Connexions.

        Navitia ne fournit pas toujours le temps réel (data_freshness =
        base_schedule) alors que G&C expose ``informationStatus`` (trainStatus,
        delay) et ``actualTime``. Retourne ``{"delay", "status", "cancelled"}``
        à partir de la première source exploitable.
        """
        import unicodedata

        for source in sources:
            if not isinstance(source, dict):
                continue
            info = source.get("informationStatus")
            info = info if isinstance(info, dict) else {}
            traffic = source.get("traffic")
            traffic = traffic if isinstance(traffic, dict) else {}

            status = info.get("trainStatus") or traffic.get("eventStatus")
            texts = [
                info.get("trainStatus"),
                traffic.get("eventStatus"),
                source.get("statusModification"),
            ]
            normalized = "".join(
                char
                for char in unicodedata.normalize(
                    "NFKD", " ".join(str(x) for x in texts if x)
                ).upper()
                if not unicodedata.combining(char)
            )
            cancelled = any(w in normalized for w in ("SUPPR", "ANNUL", "CANCEL"))

            delay = None
            raw_delay = info.get("delay")
            if isinstance(raw_delay, (int, float)) and not isinstance(raw_delay, bool):
                delay = int(raw_delay)
            elif isinstance(raw_delay, str) and raw_delay.strip().lstrip("-").isdigit():
                delay = int(raw_delay.strip())
            if delay is None:
                try:
                    actual = datetime.fromisoformat(
                        str(source.get("actualTime")).replace("Z", "+00:00")
                    )
                    scheduled = datetime.fromisoformat(
                        str(source.get("scheduledTime")).replace("Z", "+00:00")
                    )
                    delay = round((actual - scheduled).total_seconds() / 60)
                except (TypeError, ValueError):
                    delay = None

            if delay is None and not status and not cancelled:
                continue
            return {"delay": delay, "status": status, "cancelled": cancelled}
        return {"delay": None, "status": None, "cancelled": False}

    def _record_gc_live_status(self, journey: dict, *sources: Any) -> None:
        """Reporte retard / suppression G&C sur le trajet."""
        live = self._gc_live_status(*sources)
        _LOGGER.debug(
            "G&C live status for train %s: %s", get_train_num(journey), live
        )
        if live["status"]:
            journey["gc_status"] = live["status"]
        if live["cancelled"]:
            journey["status"] = "NO_SERVICE"
        elif live["delay"] is not None:
            journey["gc_delay_minutes"] = live["delay"]

    @staticmethod
    def _apply_gc_delay(journey: dict) -> None:
        """Décale départ/arrivée du retard G&C quand Navitia n'a que le théorique."""
        delay = journey.get("gc_delay_minutes")
        if (
            not isinstance(delay, int)
            or delay <= 0
            or journey.get("_gc_delay_applied")
        ):
            return
        section = next(
            (s for s in journey.get("sections") or []
             if isinstance(s, dict) and s.get("type") == "public_transport"),
            {},
        )
        departure = parse_datetime(journey.get("departure_date_time"))
        base_departure = parse_datetime(section.get("base_departure_date_time"))
        if departure and base_departure and departure != base_departure:
            return  # Navitia fournit déjà un horaire temps réel
        arrival = parse_datetime(journey.get("arrival_date_time"))
        shift = timedelta(minutes=delay)
        fmt = "%Y%m%dT%H%M%S"
        if departure:
            journey["departure_date_time"] = (departure + shift).strftime(fmt)
        if arrival:
            journey["arrival_date_time"] = (arrival + shift).strftime(fmt)
        journey["_gc_delay_applied"] = True

    async def _enrich_journeys(self, journeys: list[dict], station_uic: str) -> None:
        """Refresh live enrichment and retain last known data for each trip."""
        now = dt_util.now()
        active = []
        for journey in journeys:
            key = self._circulation_key(journey, station_uic)
            arrival = parse_datetime(journey.get("arrival_date_time"))
            if self._cancelled(journey):
                self._circulation_cache.pop(key, None)
                continue
            if arrival:
                known_delay = (
                    (self._circulation_cache.get(key) or {})
                    .get("fields", {})
                    .get("gc_delay_minutes")
                )
                if isinstance(known_delay, int) and known_delay > 0:
                    arrival += timedelta(minutes=known_delay)
            if key and arrival:
                cached = self._circulation_cache.get(key)
                if cached and cached["expires"] <= now:
                    self._circulation_cache.pop(key, None)
                if arrival > now:
                    self._circulation_cache.setdefault(key, {"fields": {}})["expires"] = arrival + timedelta(hours=1)
            if not arrival or arrival > now:
                active.append(journey)
        try:
            if active:
                await self._fetch_enrichment(active, station_uic)
        finally:
            for journey in journeys:
                key = self._circulation_key(journey, station_uic)
                cached = self._circulation_cache.get(key)
                if self._cancelled(journey):
                    self._circulation_cache.pop(key, None)
                    continue
                if not cached:
                    continue
                fields = cached["fields"]
                # Composition is a coherent snapshot: never mix two formations.
                if journey.get("train_composition"):
                    for field in ("train_composition", "train_units", "train_family",
                                  "train_type", "train_cars", "train_cars_source"):
                        fields[field] = journey.get(field)
                else:
                    journey.update({k: v for k, v in fields.items()
                                    if k.startswith("train_") and k != "train_length"})
                for field in (
                    "platform_track",
                    "arrival_platform_track",
                    "train_length",
                    "gc_delay_minutes",
                    "gc_status",
                ):
                    if journey.get(field) not in (None, "", "N/A"):
                        fields[field] = journey[field]
                    elif field in fields:
                        journey[field] = fields[field]
            for journey in journeys:
                if not self._cancelled(journey):
                    self._apply_gc_delay(journey)

    async def _fetch_enrichment(self, journeys: list[dict], station_uic: str) -> None:
        """Fetch boarding platforms and, where available, train compositions."""
        session = async_get_clientsession(self.hass)
        url = (
            "https://www.garesetconnexions.sncf/schedule-table/"
            f"Departures/{station_uic}"
        )
        timetable = []
        try:
            async with session.get(url, timeout=ClientTimeout(total=8)) as response:
                if response.status == 200:
                    timetable = await response.json(content_type=None)
                else:
                    _LOGGER.debug("G&C timetable HTTP %s", response.status)
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.debug("G&C timetable unavailable: %s", err)
        if not isinstance(timetable, list):
            timetable = []
        _LOGGER.debug("G&C station %s: %d departures", station_uic, len(timetable))

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
            candidates = list(by_number.get(number, []))
            cache_key = self._circulation_key(journey, station_uic)
            cached = self._circulation_cache.get(cache_key)
            if cached and cached.get("circulation_id"):
                saved_id = cached["circulation_id"]
                if not any(item.get("circulationId") == saved_id for item in candidates):
                    candidates.append({"circulationId": saved_id})
            if not candidates:
                _LOGGER.debug("G&C no departure match for train %s at station %s", number, station_uic)
                continue

            # Timetable items may omit JourneyStop; fetch details before matching.
            for item in candidates:
                circulation_id = item.get("circulationId")
                if not isinstance(circulation_id, str) or not circulation_id:
                    if self._matching_departure(journey, item, station_uic):
                        self._record_gc_live_status(journey, item)
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
                            timeout=ClientTimeout(total=8),
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
                # Diagnostic : données brutes G&C (retard / suppression), tronquées.
                _LOGGER.debug(
                    "G&C raw timetable item for train %s: %.3000s", number, item
                )
                _LOGGER.debug(
                    "G&C raw course detail for train %s: %.6000s", number, detail
                )
                if not self._matching_departure(journey, match_source, station_uic):
                    _LOGGER.debug("G&C time mismatch for train %s at station %s", number, station_uic)
                    continue

                if cached is not None:
                    cached["circulation_id"] = circulation_id
                stop = next(
                    (s for s in (match_source.get("JourneyStop") or [])
                     if isinstance(s, dict) and str(s.get("uic", "")).zfill(10) == station_uic),
                    None,
                )
                platform = (stop or match_source).get("platform") or {}
                if isinstance(platform, dict) and platform.get("track"):
                    journey["platform_track"] = str(platform["track"])
                self._record_gc_live_status(journey, item, stop, match_source)

                if detail:
                    # L'arrêt d'arrivée est la destination de la section train,
                    # pas forcément le terminus de la circulation.
                    arrival_uic = journey.get("arrival_uic")
                    if not arrival_uic:
                        # Appel direct (hors boucle principale) : on le déduit de
                        # la destination de la section train.
                        section = next(
                            (part for part in (journey.get("sections") or [])
                             if isinstance(part, dict)
                             and part.get("type") == "public_transport"),
                            None,
                        )
                        arrival_uic = get_stop_uic((section or {}).get("to"))
                    arrival_uic = str(arrival_uic).zfill(10) if arrival_uic else None
                    if arrival_uic:
                        arrival_stop = next(
                            (stop for stop in (detail.get("JourneyStop") or [])
                             if isinstance(stop, dict)
                             and str(stop.get("uic", "")).zfill(10) == arrival_uic),
                            None,
                        )
                        arrival_track = (arrival_stop or {}).get("platform") or {}
                        if isinstance(arrival_track, dict) and arrival_track.get("track"):
                            journey["arrival_platform_track"] = str(arrival_track["track"])
                    composition = detail.get("composition") or {}
                    elements = composition.get("element") if isinstance(
                        composition, dict
                    ) else None
                    if isinstance(elements, list):
                        journey.update(analyser_composition(elements))

                    journey["train_length"] = detail.get("trainLength")
                break
    
    @staticmethod
    def _normalize_station_name(value: Any) -> str:
        """Normalize station labels for matching API place search results."""
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value or ""))
        return " ".join(
            "".join(char for char in text if not unicodedata.combining(char))
            .casefold()
            .replace("-", " ")
            .split()
        )

    async def _resolve_station_ids(
        self, departure_name: str, arrival_name: str
    ) -> tuple[str, str] | None:
        """Resolve saved station names to the current SNCF repository IDs."""
        cache_key = (departure_name, arrival_name)
        if cache_key in self._netex_station_ids:
            return self._netex_station_ids[cache_key]

        resolved: list[str] = []
        for station_name in cache_key:
            places = await self.api_client.search_stations(station_name)
            if not places:
                _LOGGER.warning(
                    "Impossible de résoudre la gare SNCF '%s' avec le nouveau référentiel",
                    station_name,
                )
                return None

            wanted = self._normalize_station_name(station_name)
            candidates = [
                place for place in places
                if isinstance(place, dict)
                and isinstance(place.get("id"), str)
                and place["id"].startswith(("stop_area:", "stop_point:"))
            ]
            exact = next(
                (
                    place for place in candidates
                    if self._normalize_station_name(place.get("name")) == wanted
                ),
                None,
            )
            # The search endpoint can return a station label with a suffix
            # (e.g. "Paris (toutes gares)"). Never silently select an
            # unrelated result: require an exact normalized name match.
            if exact is None:
                _LOGGER.warning(
                    "Aucun résultat exact pour la gare '%s' dans le nouveau référentiel",
                    station_name,
                )
                return None
            resolved.append(exact["id"])

        result = (resolved[0], resolved[1])
        self._netex_station_ids[cache_key] = result
        return result

    def _fallback_allowed(self, subentry_id: str) -> bool:
        """Indique si le repli (horaires théoriques / nouveaux IDs) est permis."""
        return time.monotonic() >= self._fallback_retry_at.get(subentry_id, 0.0)

    async def _async_fallback_journeys(
        self, entry: Any, departure: str, arrival: str, datetime_str: str
    ) -> tuple[list | None, tuple[str, str] | None]:
        """Repli : horaires théoriques, puis résolution des nouveaux IDs.

        Retourne (trajets, nouveaux_ids). nouveaux_ids n'est renseigné que si
        les trajets ont été obtenus avec des IDs différents de ceux enregistrés.
        """
        journeys = None
        try:
            journeys = await self.api_client.fetch_journeys(
                departure, arrival, datetime_str, count=10,
                data_freshness="base_schedule",
            )
        except (ClientError, asyncio.TimeoutError, RuntimeError) as err:
            _LOGGER.warning("Horaires théoriques indisponibles : %s", err)
        if journeys:
            return journeys, None

        departure_name = entry.data.get(CONF_DEPARTURE_NAME)
        arrival_name = entry.data.get(CONF_ARRIVAL_NAME)
        if not (departure_name and arrival_name):
            return journeys, None
        if self._needs_station_name(
            departure_name, departure
        ) or self._needs_station_name(arrival_name, arrival):
            _LOGGER.warning(
                "Trajet '%s' : noms de gares absents, impossible de retrouver "
                "les nouveaux identifiants. Recréez le trajet.",
                entry.title,
            )
            return journeys, None

        new_ids = await self._resolve_station_ids(departure_name, arrival_name)
        if not new_ids or new_ids == (departure, arrival):
            return journeys, None

        _LOGGER.info(
            "Nouveaux identifiants SNCF pour '%s' : %s", entry.title, new_ids
        )
        try:
            journeys = await self.api_client.fetch_journeys(
                new_ids[0], new_ids[1], datetime_str, count=10
            )
            if not journeys:
                journeys = await self.api_client.fetch_journeys(
                    new_ids[0], new_ids[1], datetime_str,
                    count=10, data_freshness="base_schedule",
                )
        except (ClientError, asyncio.TimeoutError, RuntimeError) as err:
            _LOGGER.warning("Échec avec les nouveaux identifiants SNCF : %s", err)
            return None, None
        return journeys, new_ids if journeys else None

    def _persist_station_ids(self, subentry: Any, new_ids: tuple[str, str]) -> None:
        """Enregistre les nouveaux IDs dans la sous-entrée (meilleur effort)."""
        try:
            self.hass.config_entries.async_update_subentry(
                self.entry,
                subentry,
                data={**subentry.data, CONF_FROM: new_ids[0], CONF_TO: new_ids[1]},
            )
            _LOGGER.info(
                "Identifiants SNCF mis à jour pour '%s'", subentry.title
            )
        except Exception as err:  # noqa: BLE001 - ne doit pas casser la mise à jour
            _LOGGER.warning(
                "Impossible d'enregistrer les nouveaux identifiants : %s", err
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Récupère les données de l'API SNCF."""

        now = dt_util.now()
        self._circulation_cache = {
            key: value for key, value in self._circulation_cache.items()
            if value["expires"] > now
        }

        if not self.entry.subentries:
            _LOGGER.warning("Pas de subentries configurés")
            return {}

        update_intervals = []
        trains = {}
        pending_id_updates: list[tuple[Any, tuple[str, str]]] = []

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
            # Compatibilité avec le nouveau référentiel SNCF (NeTEx/SIRI,
            # 24/11/2026) : si rien n'est reçu, on demande les horaires
            # théoriques, puis on tente de retrouver les nouveaux IDs à partir
            # des noms de gares. Un échec complet suspend le repli pendant
            # FALLBACK_RETRY_SECONDS pour économiser le quota.
            # ---------------------------------------------------------
            if not journeys and self._fallback_allowed(subentry_id):
                journeys, new_ids = await self._async_fallback_journeys(
                    entry, departure, arrival, datetime_str
                )
                if journeys:
                    _LOGGER.warning(
                        "Trajet '%s' : aucune réponse temps réel, horaires "
                        "THÉORIQUES utilisés (retards et suppressions non "
                        "visibles)",
                        entry.title,
                    )
                    self._fallback_retry_at.pop(subentry_id, None)
                    if new_ids:
                        pending_id_updates.append((entry, new_ids))
                else:
                    self._fallback_retry_at[subentry_id] = (
                        time.monotonic() + FALLBACK_RETRY_SECONDS
                    )

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
                "Trajet '%s' : %d journey(s) reçu(s) depuis l'API "
                "(datetime demandé=%s)",
                entry.title,
                len(journeys),
                datetime_str,
            )
            for received in journeys:
                if not isinstance(received, dict):
                    continue
                received_section = next(
                    (s for s in received.get("sections") or []
                     if isinstance(s, dict) and s.get("type") == "public_transport"),
                    {},
                )
                _LOGGER.debug(
                    "Train %s : départ=%s (base=%s) data_freshness=%s statut=%s",
                    get_train_num(received),
                    received.get("departure_date_time"),
                    received_section.get("base_departure_date_time"),
                    received_section.get("data_freshness"),
                    received.get("status") or "-",
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

            # Resolve the actual boarding station from Navitia public_transport
            # sections, not from the configured origin (which may be admin:fr).
            if filtered_journeys:
                by_station: dict[str, list[dict]] = {}
                for journey in filtered_journeys:
                    sections = journey.get("sections") or []
                    section = next(
                        (item for item in sections
                         if isinstance(item, dict)
                         and item.get("type") == "public_transport"),
                        None,
                    )
                    if not section:
                        _LOGGER.debug(
                            "G&C: train %s has no public_transport section; section types=%s",
                            get_train_num(journey),
                            [part.get("type") for part in sections if isinstance(part, dict)],
                        )
                        continue
                    origin = section.get("from") or {}
                    if not isinstance(origin, dict):
                        _LOGGER.debug("G&C: invalid boarding stop for train %s", get_train_num(journey))
                        continue
                    _LOGGER.debug(
                        "G&C: train %s boarding stop IDs=%s, keys=%s",
                        get_train_num(journey), stop_identifiers(origin), list(origin),
                    )
                    uic = await self._async_stop_uic(origin)
                    station_uic = uic.zfill(10) if uic else ""
                    journey["departure_uic"] = uic
                    destination = section.get("to") or {}
                    journey["arrival_uic"] = await self._async_stop_uic(destination)
                    if station_uic:
                        by_station.setdefault(station_uic, []).append(journey)
                    else:
                        _LOGGER.debug(
                            "G&C: no UIC in boarding stop for train %s; origin=%s",
                            get_train_num(journey), origin.get("id"),
                        )
                _LOGGER.debug(
                    "G&C: resolved %d boarding stations from %d journeys",
                    len(by_station), len(filtered_journeys),
                )
                for station_uic, station_journeys in by_station.items():
                    try:
                        await self._enrich_journeys(station_journeys, station_uic)
                    except Exception as err:
                        _LOGGER.debug(
                            "G&C enrichment failed for station %s: %s",
                            station_uic, err,
                        )

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

        # Sauvegarde des IDs résolus (déclenche un rechargement de l'intégration).
        for subentry, new_ids in pending_id_updates:
            self._persist_station_ids(subentry, new_ids)

        return trains
