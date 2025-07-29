import base64
import requests

API_URL = "https://api.sncf.com/v1/coverage/sncf"

def encode_token(api_key: str) -> str:
    """Encode la clé API en base64 pour Basic Auth : clé + ":" encodé."""
    creds = f"{api_key}:"
    return base64.b64encode(creds.encode()).decode()

def search_stations(token: str, query: str):
    """Recherche des gares via l'endpoint /places (filtrage sur stop_area)."""
    headers = {"Authorization": f"Basic {token}"}
    url = f"{API_URL}/places?q={query}&type[]=stop_area"
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json().get("places", [])

def fetch_departures(token: str, stop_area_id: str, max_count: int = 20):
    """Récupère les départs en temps réel pour stop_area_id complet."""
    headers = {"Authorization": f"Basic {token}"}
    url = f"{API_URL}/stop_areas/{stop_area_id}/departures?data_freshness=realtime&count={max_count}"
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 429:
        raise Exception("Quota API dépassé (429 Too Many Requests)")
    response.raise_for_status()
    return response.json().get("departures", [])
