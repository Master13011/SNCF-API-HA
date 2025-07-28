import requests

API_URL = "https://api.sncf.com/v1/coverage/sncf"

def search_stations(token, query):
    """Recherche de stations via API SNCF avec param q=query."""
    headers = {"Authorization": f"Basic {token}"}
    r = requests.get(f"{API_URL}/stop_areas?q={query}", headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("stop_areas", [])

def fetch_departures(token, stop_area_id, max_count=20):
    """Récupère les départs en temps réel pour un stop_area donné."""
    headers = {"Authorization": f"Basic {token}"}
    url = f"{API_URL}/stop_areas/{stop_area_id}/departures?data_freshness=realtime&count={max_count}"
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("departures", [])
