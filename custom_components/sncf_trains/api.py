import base64
import logging
from aiohttp import ClientSession, ClientTimeout
from typing import List, Optional

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

    async def fetch_departures(self, stop_id: str, max_results: int = 10) -> Optional[List[dict]]:
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
                url, headers=headers, params=params, timeout=ClientTimeout(total=self._timeout)
            ) as resp:
                if resp.status == 429:
                    raise RuntimeError("Quota API exceeded (429 Too Many Requests)")
                resp.raise_for_status()
                data = await resp.json()
                return data.get("departures", [])
        except Exception as e:
            _LOGGER.error("Error fetching departures from SNCF API: %s", e)
            return None

    async def fetch_journeys(self, from_id: str, to_id: str, datetime_str: str, count: int = 5) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/journeys"
        params = {
            "from": from_id,
            "to": to_id,
            "datetime": datetime_str,
            "count": count,
            "data_freshness": "realtime",
            "datetime_represents": "departure"
        }
        params = {k: str(v) for k, v in params.items()}

        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(url, headers=headers, params=params, timeout=ClientTimeout(total=self._timeout)) as resp:
                if resp.status == 401:
                    raise RuntimeError("Unauthorized: check your API key.")
                if resp.status == 429:
                    raise RuntimeError("Quota exceeded: 429 Too Many Requests.")
                resp.raise_for_status()
                data = await resp.json()
                return data.get("journeys", [])
        except Exception as e:
            _LOGGER.error("Error fetching journeys from SNCF API: %s", e)
            return None

    async def search_stations(self, query: str) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/places"
        params = {"q": query, "type[]": "stop_point"}
        params = {k: str(v) for k, v in params.items()}
        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(url, headers=headers, params=params, timeout=ClientTimeout(total=self._timeout)) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("places", [])
        except Exception as e:
            _LOGGER.error("Error searching stations from SNCF API: %s", e)
            return None
