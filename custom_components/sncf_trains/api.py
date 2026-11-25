import base64
import logging
from aiohttp import ClientSession, ClientTimeout, ClientError
from typing import List, Optional, Mapping
from homeassistant.exceptions import ConfigEntryAuthFailed
import asyncio

from .helpers import attach_disruptions, uic_from_codes

API_BASE = "https://api.sncf.com"
_LOGGER = logging.getLogger(__name__)


def encode_token(api_key: str) -> str:
    """Encode the API key for Basic Auth."""
    token_str = f"{api_key}:"
    return base64.b64encode(token_str.encode()).decode()


class SncfApiClient:
    def __init__(self, session: ClientSession, api_key: str, timeout: int = 10):
        self._session = session
        self._token = encode_token(api_key)
        self._timeout = timeout

    async def fetch_departures(
        self, stop_id: str, max_results: int = 10
    ) -> Optional[List[dict]]:
        if stop_id.startswith("stop_area:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_areas/{stop_id}/departures"
        elif stop_id.startswith("stop_point:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_points/{stop_id}/departures"
        else:
            raise ValueError("stop_id must start with 'stop_area:' or 'stop_point:'")

        params_raw: dict[str, object] = {
            "data_freshness": "realtime",
            "count": max_results,
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}

        headers = {"Authorization": f"Basic {self._token}"}

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    # vrai problème d'auth
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status == 429:
                    # rate-limit => pas une auth failure
                    _LOGGER.warning("API rate limit (429) on %s with %s", url, params)
                    raise RuntimeError(
                        "SNCF API rate-limited (429)"
                    )  # sera géré comme non-critique
                resp.raise_for_status()
                data = await resp.json()
                return data.get("departures", [])
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Network error fetching departures from SNCF API: %s", err)
            _LOGGER.debug("URL: %s, Params: %s", url, params)
            return None

    async def fetch_journeys(
        self, from_id: str, to_id: str, datetime_str: str, count: int = 5,
        data_freshness: str = "realtime",
    ) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/journeys"
        params_raw: dict[str, object] = {
            "from": from_id,
            "to": to_id,
            "datetime": datetime_str,
            "count": count,
            "data_freshness": data_freshness,
            "datetime_represents": "departure",
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}

        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status == 429:
                    raise RuntimeError("Quota exceeded: 429 Too Many Requests.")
                resp.raise_for_status()
                data = await resp.json()
                journeys = data.get("journeys", [])
                attach_disruptions(journeys, data.get("disruptions", []))
                return journeys
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Network error fetching journeys from SNCF API: %s", err)
            return None

    async def search_stations(self, query: str) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/places"
        params_raw: dict[str, object] = {
            "q": query,
            "type[]": "stop_point",
            # L'API peut ignorer type[] : on demande plus de résultats pour que
            # les gares ne soient pas noyées parmi communes/adresses.
            "count": 25,
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}
        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("places", [])
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Network error searching stations from SNCF API: %s", err)
            return None

    async def fetch_station_name(self, stop_id: str) -> Optional[str]:
        """Return the display name of a stop (as shown by the places search).

        Used to backfill station names of journeys saved before names were
        stored. Returns None if the stop is unknown or the request fails.
        """
        if stop_id.startswith("stop_area:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_areas/{stop_id}"
            key = "stop_areas"
        elif stop_id.startswith("stop_point:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_points/{stop_id}"
            key = "stop_points"
        else:
            return None

        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                data = await resp.json()
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Network error fetching station %s: %s", stop_id, err)
            return None

        items = data.get(key) or []
        if not items or not isinstance(items[0], dict):
            return None
        stop = items[0]
        name = stop.get("name")
        if not name:
            return None
        # The places search labels stops "Name (City)"; rebuild that label.
        regions = stop.get("administrative_regions") or []
        city = next(
            (r.get("name") for r in regions if isinstance(r, dict) and r.get("level") == 8),
            None,
        ) or next((r.get("name") for r in regions if isinstance(r, dict) and r.get("name")), None)
        return f"{name} ({city})" if city else name

    async def fetch_stop_uic(self, stop_id: str) -> Optional[str]:
        """Return the UIC code of a stop (stop_point or stop_area), if known.

        Used when the journey response does not embed the ``codes`` of a stop
        (this can happen for border stations such as Monaco).
        """
        if stop_id.startswith("stop_area:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_areas/{stop_id}"
            key = "stop_areas"
        elif stop_id.startswith("stop_point:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_points/{stop_id}"
            key = "stop_points"
        else:
            return None

        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status in (404, 429):
                    return None
                resp.raise_for_status()
                data = await resp.json()
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Network error fetching UIC of %s: %s", stop_id, err)
            return None

        items = data.get(key) or []
        if not items or not isinstance(items[0], dict):
            return None
        stop = items[0]
        uic = uic_from_codes(stop.get("codes"))
        if uic:
            return uic
        area = stop.get("stop_area")
        return uic_from_codes(area.get("codes")) if isinstance(area, dict) else None
