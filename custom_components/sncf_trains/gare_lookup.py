import aiohttp

async def find_station_code(query, api_key):
    url = f"https://api.sncf.com/v1/coverage/sncf/places?q={query}&type[]=stop_area"
    headers = {"Authorization": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            for place in data.get("places", []):
                if "stop_area" in place:
                    return place["stop_area"]["id"].split(":")[-1]
    return None