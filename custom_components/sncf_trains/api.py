import base64
import aiohttp
import logging

API_BASE = "https://api.sncf.com"
_LOGGER = logging.getLogger(__name__)

def encode_token(api_key: str) -> str:
    """Encode the API key for Basic Auth."""
    token_str = f"{api_key}:"
    return base64.b64encode(token_str.encode()).decode()

async def fetch_departures(token: str, stop_id: str, max_results: int = 10):
    """
    Fetch departures from a stop_area or stop_point.
    Automatically selects the correct endpoint based on stop_id prefix.
    """
    if stop_id.startswith("stop_area:"):
        url = f"{API_BASE}/v1/coverage/sncf/stop_areas/{stop_id}/departures"
    elif stop_id.startswith("stop_point:"):
        url = f"{API_BASE}/v1/coverage/sncf/stop_points/{stop_id}/departures"
    else:
        raise ValueError("stop_id must start with 'stop_area:' or 'stop_point:'")

    params = {
        "data_freshness": "realtime",
        "count": max_results
    }
    headers = {"Authorization": f"Basic {token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                if resp.status == 429:
                    raise RuntimeError("Quota API exceeded (429 Too Many Requests)")
                resp.raise_for_status()
                data = await resp.json()
                return data.get("departures", [])
    except Exception as e:
        _LOGGER.error("Error fetching departures from SNCF API: %s", e)
        return []

async def search_stations(token: str, query: str):
    """
    Search for stop_points matching a query string.
    Returns a list of stop_point objects.
    """
    url = f"{API_BASE}/v1/coverage/sncf/places"
    params = {
        "q": query,
        "type[]": "stop_point"
    }
    headers = {"Authorization": f"Basic {token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("places", [])
    except Exception as e:
        _LOGGER.error("Error searching stations from SNCF API: %s", e)
        return []
