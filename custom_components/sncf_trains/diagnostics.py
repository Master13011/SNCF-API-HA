"""Diagnostics support for SNCF integration."""

from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_registry import async_redact_data
from .const import DOMAIN, CONF_API_KEY

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {}

    data["config_entry"] = {
        "title": entry.title,
        "data": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
        "entry_id": entry.entry_id,
        "version": entry.version,
    }

    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        data["coordinator"] = {
            "departure": getattr(coordinator, "departure", None),
            "arrival": getattr(coordinator, "arrival", None),
            "time_start": getattr(coordinator, "time_start", None),
            "time_end": getattr(coordinator, "time_end", None),
            "update_interval": str(getattr(coordinator, "update_interval", None)),
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "last_update_time": str(
                getattr(coordinator, "last_update_success_time", None)
            ),
            "data_sample": (
                coordinator.data[:3]
                if hasattr(coordinator, "data") and coordinator.data
                else None
            ),
        }
    return data
