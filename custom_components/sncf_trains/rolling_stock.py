"""Identification prudente du matériel roulant voyageurs français.

Les nombres de caisses sont renseignés uniquement pour les séries à longueur
stable. Les séries à variantes ne sont pas estimées à partir du numéro seul.
Le matériel tracté n'a pas de nombre de voitures déductible de sa locomotive.
"""

import re
from typing import Any

# Début, fin, désignation française, famille, caisses par élément (ou None).
# Les plages sont inclusives. Elles concernent le numéro d'engin, pas un UIC.
MATERIELS_ROULANTS: dict[str, list[tuple[int, int, str, str, int | None]]] = {
    "Z": [
        (7300, 7399, "Automotrice Z2", "Z2", 2),
        (7500, 7599, "Automotrice Z2", "Z2", 2),
        (9500, 9599, "Automotrice Z2", "Z2", 2),
        (9600, 9699, "Automotrice Z2", "Z2", 2),
        (11500, 11599, "Automotrice Z2", "Z2", 2),
        (20500, 20899, "Z 2N", "Z 20500", None),
        (20900, 20999, "Z 2N", "Z 20900", 4),
        (21500, 21699, "Z TER", "Z 21500", 3),
        (22500, 22599, "MI 2N", "Z 22500", 5),
        (23500, 23599, "TER 2N", "Z 23500", 2),
        (24500, 24799, "TER 2N NG", "Z 24500", None),
        (26500, 26699, "TER 2N NG", "Z 26500", None),
        (27500, 27999, "ZGC (AGC)", "AGC", None),
        (31500, 31599, "Régiolis Léman Express", "Régiolis", 4),
        (41000, 41099, "Régiolis", "Régiolis", None),
        (50000, 50999, "Francilien", "Z 50000", None),
        (51500, 51999, "Régiolis", "Régiolis", None),
        (54500, 54899, "Régiolis", "Régiolis", None),
        (54900, 54999, "Régiolis", "Régiolis", None),
        (55500, 55999, "Régio2N", "Régio2N", None),
        (56000, 56499, "Régio2N", "Régio2N", None),
        (56500, 56999, "Omneo Premium (Régio2N)", "Régio2N", None),
        (57000, 57999, "Régio2N", "Régio2N", None),
        (58000, 58999, "RER NG", "RER NG", None),
        (59000, 59999, "Régio2N", "Régio2N", None),
    ],
    "X": [
        (2100, 2199, "Autorail X 2100", "X 2100", None),
        (2200, 2299, "Autorail X 2200", "X 2200", None),
        (2800, 2899, "Autorail X 2800", "X 2800", None),
        (72500, 72999, "X TER", "X 72500", None),
        (73500, 73999, "ATER", "X 73500 / X 73900", 1),
        (76500, 76999, "XGC (AGC)", "AGC", None),
    ],
    "B": [
        (81500, 81999, "BGC (AGC)", "AGC", None),
        (82500, 82999, "Bibi (AGC)", "AGC", 4),
        (83500, 83999, "Régiolis", "Régiolis", None),
        (84500, 84999, "Régiolis", "Régiolis", None),
        (85000, 85499, "Coradia Liner", "Régiolis", 6),
        (85500, 85999, "Régiolis", "Régiolis", None),
    ],
    "U": [
        (25500, 25599, "Avanto", "Tram-train", 5),
        (53500, 53999, "Citadis Dualis", "Tram-train", 4),
    ],
    "TGV": [
        # Le numéro de rame TGV seul ne désigne pas universellement une série.
        # Reconnaissance uniquement lorsque la famille est explicite.
    ],
    "BB": [
        (15000, 15999, "Locomotive BB 15000", "Locomotive", None),
        (22200, 22399, "Locomotive BB 22200", "Locomotive", None),
        (26000, 26999, "Locomotive BB 26000", "Locomotive", None),
        (27000, 27999, "Locomotive BB 27000", "Locomotive", None),
        (67400, 67999, "Locomotive BB 67400", "Locomotive", None),
    ],
}

# Nombre de voitures uniquement pour un matériel explicitement identifié.
# Une rame TGV classique à deux motrices encadre généralement huit remorques,
# mais cela ne peut pas être déduit de manière sûre d'un identifiant numérique nu.
TGV_EXPLICITES: dict[str, tuple[str, int | None]] = {
    "TGV ATLANTIQUE": ("TGV Atlantique", 10),
    "TGV RESEAU": ("TGV Réseau", 8),
    "TGV RÉSEAU": ("TGV Réseau", 8),
    "TGV DUPLEX": ("TGV Duplex", 8),
    "TGV POS": ("TGV POS", 8),
    "TGV EURODUPLEX": ("TGV Euroduplex", 8),
    "TGV OCEANE": ("TGV Océane", 8),
    "TGV OCÉANE": ("TGV Océane", 8),
    "TGV M": ("TGV M", None),
}


def identifier_materiel(reference: str) -> dict[str, Any] | None:
    """Reconnaît une rame sans déduire abusivement sa version."""
    raw = str(reference).upper().strip()
    for prefix, (nom, caisses) in TGV_EXPLICITES.items():
        if raw.startswith(prefix):
            return {
                "reference": raw,
                "type": nom,
                "famille": "TGV",
                "voitures": caisses,
                "source": "catalogue" if caisses is not None else "inconnue",
            }

    # Évite de lire les chiffres d'un UIC comme une référence de rame.
    match = re.search(
        r"(?<![A-Z0-9])(BB|[ZBXU])[ ]*([0-9]{4,5})([ML])?(?![A-Z0-9])",
        raw,
    )
    if not match:
        return None
    prefix, number, suffix = match.groups()
    numeric = int(number)
    for debut, fin, nom, famille, voitures in MATERIELS_ROULANTS[prefix]:
        if debut <= numeric <= fin:
            # M/L n'est interprété que lorsque cette variante est explicite.
            if famille == "Régiolis" and suffix in ("M", "L"):
                voitures = 4 if suffix == "M" else 6
            return {
                "reference": f"{prefix}{number}",
                "type": nom,
                "famille": famille,
                "voitures": voitures,
                "source": "catalogue" if voitures is not None else "inconnue",
            }
    return None


def analyser_composition(elements: list) -> dict[str, Any]:
    """Somme les caisses connues, sans assimiler locomotive et voiture."""
    rames = [
        element.get("numeroAffectation")
        for element in elements
        if isinstance(element, dict)
        and isinstance(element.get("numeroAffectation"), str)
        and element["numeroAffectation"]
    ]
    materiels = [identifier_materiel(rame) for rame in rames]
    connus = [m for m in materiels if m is not None]
    familles = {m["famille"] for m in connus}
    types = {m["type"] for m in connus}
    complet = len(rames) == len(elements) and len(connus) == len(elements)
    voitures = (
        sum(m["voitures"] for m in materiels)
        if complet and all(m["voitures"] is not None for m in materiels)
        else None
    )
    return {
        "train_units": len(elements),
        "train_composition": rames,
        "train_family": next(iter(familles)) if complet and len(familles) == 1 else None,
        "train_type": next(iter(types)) if complet and len(types) == 1 else None,
        "train_cars": voitures,
        "train_cars_source": "catalogue" if voitures is not None else "inconnue",
    }
