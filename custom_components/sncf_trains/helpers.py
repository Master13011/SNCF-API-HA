"""Helpers for component."""

import re
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def parse_datetime(dt_str: str) -> datetime | None:
    """Parse string to datetime."""
    if not dt_str:
        return None

    try:
        dt = dt_util.parse_datetime(dt_str)
        return dt_util.as_local(dt) if dt else None
    except (ValueError, TypeError):
        return None


def format_time(dt_str: str) -> str:
    """Format a Navitia datetime string as dd/mm/YYYY - HH:MM."""
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else "N/A"


def get_train_num(journey: dict[str, Any]) -> str:
    """Extract the commercial train number from a journey."""
    # ---------------------------------------------------------
    # 1. Le journey peut directement contenir le numéro
    # ---------------------------------------------------------
    trip_num = journey.get("trip_short_name")

    if trip_num:
        return str(trip_num)

    # ---------------------------------------------------------
    # 2. Cherche dans les sections
    #
    # Les nouveaux trajets peuvent avoir par exemple :
    #
    # section[0] = crow_fly / walking
    # section[1] = public_transport
    # section[2] = crow_fly / walking
    #
    # Il ne faut donc plus supposer que sections[0] est le train.
    # ---------------------------------------------------------
    sections = journey.get("sections", [])

    if not isinstance(sections, list):
        return ""

    # ---------------------------------------------------------
    # 3. Priorité aux sections public_transport
    # ---------------------------------------------------------
    for section in sections:
        if not isinstance(section, dict):
            continue

        if section.get("type") != "public_transport":
            continue

        infos = section.get("display_informations", {})

        if not isinstance(infos, dict):
            continue

        trip_num = infos.get("trip_short_name")

        if trip_num:
            return str(trip_num)

        trip_num = infos.get("num")

        if trip_num:
            return str(trip_num)

    # ---------------------------------------------------------
    # 4. Fallback : chercher dans n'importe quelle section
    #
    # Utile pour conserver la compatibilité avec les anciens
    # formats de réponse API.
    # ---------------------------------------------------------
    for section in sections:
        if not isinstance(section, dict):
            continue

        infos = section.get("display_informations", {})

        if not isinstance(infos, dict):
            continue

        trip_num = infos.get("trip_short_name")

        if trip_num:
            return str(trip_num)

        trip_num = infos.get("num")

        if trip_num:
            return str(trip_num)

    # ---------------------------------------------------------
    # 5. Aucun numéro trouvé
    # ---------------------------------------------------------
    return ""


def get_duration(journey: dict[str, Any]) -> int:
    """Compute journey duration in minutes."""
    dep = parse_datetime(journey.get("departure_date_time", ""))

    arr = parse_datetime(journey.get("arrival_date_time", ""))

    if dep and arr:
        return int((arr - dep).total_seconds() / 60)

    return 0


def attach_disruptions(journeys: list, disruptions: list) -> None:
    """Link the response-level disruptions to the journeys they affect."""
    by_id = {}
    for disruption in disruptions:
        if not isinstance(disruption, dict):
            continue
        for key in ("id", "disruption_id", "impact_id"):
            if disruption.get(key):
                by_id[disruption[key]] = disruption

    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        found = []
        for section in journey.get("sections") or []:
            if not isinstance(section, dict):
                continue
            display = section.get("display_informations")
            links = list(section.get("links") or [])
            if isinstance(display, dict):
                links += display.get("links") or []
            for link in links:
                if not isinstance(link, dict) or link.get("type") != "disruption":
                    continue
                disruption = by_id.get(link.get("id"))
                if disruption is not None and disruption not in found:
                    found.append(disruption)
        journey["disruptions"] = found


def disruption_summary(journey: dict) -> dict:
    """Return the cause, effect and message of a journey's main disruption."""
    summary = {"disruption_cause": None, "disruption_effect": None,
               "disruption_message": None}
    disruptions = journey.get("disruptions") or []
    if not disruptions:
        return summary
    main = disruptions[0]
    cause = main.get("cause") or None
    if not cause:
        for impacted in main.get("impacted_objects") or []:
            for stop in (impacted.get("impacted_stops") or []):
                if stop.get("cause"):
                    cause = stop["cause"]
                    break
            if cause:
                break
    severity = main.get("severity") or {}
    messages = main.get("messages") or []
    summary["disruption_cause"] = cause
    summary["disruption_effect"] = severity.get("effect")
    summary["disruption_message"] = messages[0].get("text") if messages else None
    return summary


# ---------------------------------------------------------------------------
# UIC des gares
#
# Depuis le nouveau référentiel SNCF (NeTEx), les identifiants ressemblent à
#   stop_point:SNC:VSP:FR::LMU:6c1a3b10-cb0a-11e8-8bfa-f784c1c7c611:
# et ne contiennent plus le code UIC. Celui-ci est fourni dans la liste
# ``codes`` de l'objet : {"type": "UIC", "value": "87756056"}.
# ---------------------------------------------------------------------------

_UIC_CODE_TYPES = {"uic", "uic8", "uic_code"}
# Ni lettre, chiffre ni tiret autour : évite de lire le début d'un UUID NeTEx
# (ex. "91653280-cb0a-...") comme un UIC.
_UIC_IN_ID = re.compile(r"(?<![0-9A-Za-z-])([0-9]{8}|00[0-9]{8})(?![0-9A-Za-z-])")


def _normalize_uic(value: Any) -> str | None:
    """Return the UIC as 7-8 digits without leading zeros, or None."""
    digits = re.sub(r"\D", "", str(value or "")).lstrip("0")
    return digits if 7 <= len(digits) <= 8 else None


def uic_from_codes(codes: Any) -> str | None:
    """Return the UIC found in a Navitia ``codes`` list."""
    if not isinstance(codes, list):
        return None
    for code in codes:
        if not isinstance(code, dict):
            continue
        if str(code.get("type", "")).casefold() in _UIC_CODE_TYPES:
            uic = _normalize_uic(code.get("value"))
            if uic:
                return uic
    return None


def stop_identifiers(place: Any) -> list[str]:
    """Return every stop_point / stop_area / place id carried by a place."""
    if not isinstance(place, dict):
        return []
    ids: list[str] = []
    for obj in (
        place,
        place.get("stop_point"),
        place.get("stop_area"),
    ):
        if isinstance(obj, dict) and isinstance(obj.get("id"), str):
            if obj["id"] not in ids:
                ids.append(obj["id"])
    return ids


# Gares dont l'API SNCF ne fournit pas de code UIC (gares hors France, p. ex.
# Monaco). Clé : identifiant NeTEx (partie UUID) ou nom de gare normalisé.
_UIC_FALLBACK_BY_NETEX = {
    "91653280-cb0a-11e8-8bfa-f784c1c7c611": "87756403",  # Monaco-Monte-Carlo
}
_UIC_FALLBACK_BY_NAME = {
    "monaco monte carlo": "87756403",
    "ventimiglia": "83045013",
    "vintimille": "83045013",
    "geneve cornavin": "85010082",
    "geneve": "85010082",
    "basel sbb": "85000109",
    "bale sbb": "85000109",
    "bale cff": "85000109",
    "basel st johann": "87187930",
}


def _fallback_uic(place: dict) -> str | None:
    """Return a known UIC for stations that carry none in the API."""
    for identifier in stop_identifiers(place):
        for uuid, uic in _UIC_FALLBACK_BY_NETEX.items():
            if uuid in identifier:
                return uic
    for obj in (place.get("stop_point"), place):
        name = obj.get("name") if isinstance(obj, dict) else None
        if isinstance(name, str):
            key = re.sub(r"\s*\(.*?\)\s*", " ", name).replace("-", " ")
            key = " ".join(key.casefold().split())
            if key in _UIC_FALLBACK_BY_NAME:
                return _UIC_FALLBACK_BY_NAME[key]
    return None


def get_stop_uic(place: Any) -> str | None:
    """Extract the UIC of a journey section ``from`` / ``to`` place.

    Order: ``codes`` of the stop_point, of the stop_area, of the place itself,
    then (legacy IDs) an 8-digit UIC embedded in one of the identifiers.
    """
    if not isinstance(place, dict):
        return None
    for obj in (place.get("stop_point"), place.get("stop_area"), place):
        if isinstance(obj, dict):
            uic = uic_from_codes(obj.get("codes"))
            if uic:
                return uic
    known = _fallback_uic(place)
    if known:
        return known
    for identifier in stop_identifiers(place):
        found = _UIC_IN_ID.search(identifier)
        if found:
            return found.group(1).lstrip("0")
    return None
