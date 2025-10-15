"""Helpers for componnet."""

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def parse_datetime(dt_str: str) -> datetime | None:
    """Parse string to datetime."""
    if not dt_str:
        return None
    try:
        dt = dt_util.parse_datetime(dt_str)  # parse with timezone info if possible
        return dt_util.as_local(dt) if dt else None  # convert to local timezone
    except Exception:
        return None


def format_time(dt_str: str) -> str:
    """Format a Navitia datetime string as dd/mm/YYYY - HH:MM."""
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else "N/A"


def get_train_num(journey: dict[str, Any]) -> str:
    """Extract the commercial train number."""
    trip_num = journey.get("trip_short_name")
    if trip_num:
        return trip_num
    sections = journey.get("sections", [])
    if sections:
        infos = sections[0].get("display_informations", {})
        return infos.get("trip_short_name") or infos.get("num", "")
    return ""


def get_duration(journey: dict) -> int:
    """Compute journey duration in minutes."""
    dep = parse_datetime(journey.get("departure_date_time", ""))
    arr = parse_datetime(journey.get("arrival_date_time", ""))
    if dep and arr:
        return int((arr - dep).total_seconds() / 60)
    return 0
