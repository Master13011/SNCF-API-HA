"""Diagnostics support for SNCF integration."""
from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {}

    # Données de config
    data["config_entry"] = {
        "title": entry.title,
        "data": {k: ("***" if "api" in k else v) for k, v in entry.data.items()},
        "options": entry.options,
        "entry_id": entry.entry_id,
        "version": entry.version,
    }

    # Récupère le coordinator s’il existe
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        data["coordinator"] = {
            "departure": coordinator.departure,
            "arrival": coordinator.arrival,
            "time_start": coordinator.time_start,
            "time_end": coordinator.time_end,
            "update_interval": str(coordinator.update_interval),
            "last_update_success": coordinator.last_update_success,
            "last_update_time": str(coordinator.last_update_success_time),
            "data_sample": coordinator.data[:3] if coordinator.data else None,
        }

    return data
