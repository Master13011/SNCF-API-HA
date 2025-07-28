import aiohttp
from datetime import datetime
from .const import SNCF_API_BASE

async def fetch_departures(api_key, station_code, from_dt, to_dt):
    headers = {"Authorization": api_key}
    results = []
    async with aiohttp.ClientSession() as session:
        url = f"{SNCF_API_BASE}/stop_areas/stop_area:SNCF:{station_code}/departures?from_datetime={from_dt.strftime('%Y%m%dT%H%M%S')}&duration=7200"
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for d in data.get("departures", []):
                stop_time = d["stop_date_time"]
                dt = datetime.strptime(stop_time["departure_date_time"], "%Y%m%dT%H%M%S")
                delay = int(stop_time.get("departure_delay", 0)) // 60
                status = d.get("status", "on time")
                if status == "cancelled":
                    status_text = "Annulé"
                elif delay > 0:
                    status_text = f"Retardé {delay} min"
                else:
                    status_text = "À l'heure"

                results.append({
                    "heure": dt.strftime("%H:%M"),
                    "destination": d["display_informations"]["direction"],
                    "train": d["display_informations"]["headsign"],
                    "mode": d["display_informations"].get("commercial_mode", "train"),
                    "status": status_text
                })
    return results