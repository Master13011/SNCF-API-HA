"""Diagnostics support for SNCF integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_redact_data

from .const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    DOMAIN,
)
from .helpers import get_train_num


TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {}

    # -----------------------------------------------------------------
    # Configuration de l'intégration
    # -----------------------------------------------------------------
    data["config_entry"] = {
        "title": entry.title,
        "data": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
        "entry_id": entry.entry_id,
        "version": entry.version,
    }

    # -----------------------------------------------------------------
    # Récupération du coordinator
    # -----------------------------------------------------------------
    coordinator = entry.runtime_data

    if coordinator is None:
        data["coordinator"] = {
            "available": False,
            "reason": "Coordinator non disponible",
        }
        return data

    # -----------------------------------------------------------------
    # Informations générales du coordinator
    # -----------------------------------------------------------------
    coordinator_data = getattr(coordinator, "data", {}) or {}

    data["coordinator"] = {
        "available": coordinator.last_update_success,
        "last_update_success": coordinator.last_update_success,
        "last_update_time": str(
            getattr(
                coordinator,
                "last_update_success_time",
                None,
            )
        ),
        "update_interval": str(
            getattr(
                coordinator,
                "update_interval",
                None,
            )
        ),
        "update_interval_minutes": getattr(
            coordinator,
            "update_interval_minutes",
            None,
        ),
        "outside_interval_minutes": getattr(
            coordinator,
            "outside_interval_minutes",
            None,
        ),
        "subentries_count": len(entry.subentries),
        "data_subentries_count": len(coordinator_data),
    }

    # -----------------------------------------------------------------
    # Diagnostic de chaque trajet configuré
    # -----------------------------------------------------------------
    subentries_data: dict[str, Any] = {}

    for subentry_id, subentry in entry.subentries.items():
        journeys = coordinator_data.get(subentry_id, [])

        if not isinstance(journeys, list):
            journeys = []

        departure = subentry.data.get(CONF_FROM)
        arrival = subentry.data.get(CONF_TO)
        time_start = subentry.data.get(CONF_TIME_START)
        time_end = subentry.data.get(CONF_TIME_END)

        subentry_info: dict[str, Any] = {
            "title": subentry.title,
            "subentry_id": subentry_id,
            "departure": departure,
            "arrival": arrival,
            "time_start": time_start,
            "time_end": time_end,
            "journeys_count": len(journeys),
            "journeys": [],
        }

        # -------------------------------------------------------------
        # Informations sur les journeys retournés par l'API
        # -------------------------------------------------------------
        for journey_index, journey in enumerate(journeys[:10]):
            if not isinstance(journey, dict):
                subentry_info["journeys"].append(
                    {
                        "index": journey_index,
                        "invalid": True,
                        "value_type": type(journey).__name__,
                    }
                )
                continue

            sections = journey.get("sections", [])

            if not isinstance(sections, list):
                sections = []

            journey_info: dict[str, Any] = {
                "index": journey_index,
                "departure_date_time": journey.get("departure_date_time"),
                "arrival_date_time": journey.get("arrival_date_time"),
                "requested_date_time": journey.get("requested_date_time"),
                "duration": journey.get("duration"),
                "nb_transfers": journey.get("nb_transfers"),
                "type": journey.get("type"),
                "status": journey.get("status"),
                "tags": journey.get("tags"),
                "train_num": get_train_num(journey),
                "sections_count": len(sections),
                "sections": [],
            }

            # ---------------------------------------------------------
            # Informations sur les sections
            # ---------------------------------------------------------
            for section_index, section in enumerate(sections):
                if not isinstance(section, dict):
                    journey_info["sections"].append(
                        {
                            "index": section_index,
                            "invalid": True,
                            "value_type": type(section).__name__,
                        }
                    )
                    continue

                display_info = section.get(
                    "display_informations",
                    {},
                )

                if not isinstance(display_info, dict):
                    display_info = {}

                section_info: dict[str, Any] = {
                    "index": section_index,
                    "id": section.get("id"),
                    "type": section.get("type"),
                    "mode": section.get("mode"),
                    "departure_date_time": section.get("departure_date_time"),
                    "arrival_date_time": section.get("arrival_date_time"),
                    "duration": section.get("duration"),
                    "display_informations": {
                        "commercial_mode": display_info.get("commercial_mode"),
                        "physical_mode": display_info.get("physical_mode"),
                        "direction": display_info.get("direction"),
                        "trip_short_name": display_info.get("trip_short_name"),
                        "num": display_info.get("num"),
                    },
                }

                journey_info["sections"].append(section_info)

            subentry_info["journeys"].append(journey_info)

        subentries_data[subentry_id] = subentry_info

    data["subentries"] = subentries_data

    return data
