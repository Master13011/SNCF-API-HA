"""Module de gestion des correspondances et corrections d'identifiants gares."""
import logging
import re

_LOGGER = logging.getLogger(__name__)

# Table de correspondance statique d'urgence (ID strict vers UIC d'affichage)
CORRESPONDANCE_ID_STRICT = {
    "stop_area:snc:fr::lmo:91653280-cb0a-11e8-8bfa-f784c1c7c611:": "0087756403",  # Monaco Monte-Carlo
    "stop_area:snc:fr::lmo:a260cb70-337a-11e9-b154-294c36c22c4f:": "0087756247",  # Ventimiglia (Vintimille)
}

def filtrer_uic_gare(place: dict) -> str:
    """Analyse les données d'une gare et extrait le code UIC français adapté.
    
    Gère le mapping des gares frontalières (Monaco, Vintimille, etc.) pour Gares & Connexions.
    Retourne une chaîne vide si aucun UIC ou correspondance n'est trouvé.
    """
    if not isinstance(place, dict):
        return ""

    # 1. Extraction des éléments textuels pour les vérifications de sécurité
    station_name = (
        (place.get("stop_area") or {}).get("name")
        if isinstance(place.get("stop_area"), dict)
        else None
    ) or place.get("name")

    station_id = str(place.get("id") or "").lower().strip()

    # 2. Vérification par ID strict (Clé de secours NeTEx)
    if station_id in CORRESPONDANCE_ID_STRICT:
        _LOGGER.debug("Correspondance par ID trouvée pour %s -> %s", station_id, CORRESPONDANCE_ID_STRICT[station_id])
        return CORRESPONDANCE_ID_STRICT[station_id]

    # 3. Interception par mot-clé textuel (Nom ou ID)
    if isinstance(station_name, str) and station_name.strip():
        normalized_name = station_name.lower()
        
        if "monaco" in normalized_name or "91653280" in station_id:
            return "0087756403"
        elif "ventimiglia" in normalized_name or "vintimille" in normalized_name or "83045013" in station_id:
            return "0087756247"
        elif "basel" in normalized_name or "bâle" in normalized_name:
            return "0087181008"
        elif "geneve" in normalized_name or "genève" in normalized_name:
            return "0087747006"

    # 4. Extraction classique standard depuis le tableau 'codes' (Pour 95% des gares françaises)
    uic_found = ""
    for target in (place, place.get("stop_point"), place.get("stop_area")):
        if not isinstance(target, dict):
            continue
        for code in target.get("codes") or []:
            if isinstance(code, dict) and str(code.get("type", "")).lower() in ("uic", "source"):
                val = str(code.get("value", "")).strip()
                if val.isdigit() and len(val) in (8, 10):
                    uic_found = val.zfill(10)
                    break
        if uic_found:
            break

    # 5. Repli par Regex classique dans l'ID si aucun code explicite n'est extrait
    if not uic_found:
        identifiers = [
            place.get("id"),
            (place.get("stop_point") or {}).get("id") if isinstance(place.get("stop_point"), dict) else None,
            (place.get("stop_area") or {}).get("id") if isinstance(place.get("stop_area"), dict) else None,
        ]
        for identifier in identifiers:
            if not isinstance(identifier, str):
                continue
            match = re.search(r"(?<![0-9])([0-9]{8}|00[0-9]{8})(?![0-9])", identifier)
            if match:
                uic_found = match.group(1).zfill(10)
                break

    return uic_found
