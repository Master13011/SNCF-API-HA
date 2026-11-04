"""Catalogue français conservateur des matériels roulants SNCF.

Le numéro de série identifie une famille, pas toujours une longueur.
Ne jamais inventer le nombre de caisses lorsqu'une série possède plusieurs
configurations. Les suffixes M (4 caisses) et L (6 caisses) sont utilisés
uniquement pour les Régiolis lorsque présents dans l'identifiant.
"""

import re
from typing import Any

# (désignation, famille, nombre de caisses par rame ou None si variable)
MATERIELS_ROULANTS: dict[str, tuple[str, str, int | None]] = {
    # TER 2N NG : série tricaisse.
    "Z24500": ("TER 2N NG", "Z 24500", 3),
    # AGC : variantes à trois et quatre caisses selon les séries et les parcs.
    "X76500": ("XGC (AGC)", "AGC", None),
    "Z27500": ("ZGC (AGC)", "AGC", None),
    "B81500": ("BGC (AGC)", "AGC", None),
    "B82500": ("Bibi (AGC)", "AGC", 4),
    # Régiolis : la longueur dépend de la variante de chaque élément.
    "B83500": ("Régiolis", "Régiolis", None),
    "B83600": ("Régiolis", "Régiolis", 6),
    "B84500": ("Régiolis", "Régiolis", None),
    "B84800": ("Régiolis", "Régiolis", 4),
    "B84900": ("Régiolis", "Régiolis", None),
    "B85000": ("Coradia Liner (Régiolis)", "Régiolis", 6),
    "B85500": ("Régiolis", "Régiolis", 4),
    "B85900": ("Régiolis", "Régiolis", None),
    "Z31500": ("Régiolis Léman Express", "Régiolis", 4),
    "Z41000": ("Régiolis", "Régiolis", 4),
    "Z51500": ("Régiolis", "Régiolis", None),
    "Z54500": ("Régiolis", "Régiolis", 6),
    "Z54900": ("Régiolis", "Régiolis", 4),
    # Régio2N : Z55500 et plusieurs autres séries ont plusieurs longueurs.
    "Z55500": ("Régio2N", "Régio2N", None),
    "Z56000": ("Régio2N", "Régio2N", None),
    "Z56300": ("Régio2N", "Régio2N", None),
    "Z56400": ("Régio2N", "Régio2N", None),
    "Z56500": ("Omneo Premium (Régio2N)", "Régio2N", 8),
    "Z56600": ("Omneo Premium (Régio2N)", "Régio2N", 10),
    "Z56700": ("Omneo Premium (Régio2N)", "Régio2N", 8),
    "Z56800": ("Omneo Premium (Régio2N)", "Régio2N", 10),
    "Z57000": ("Régio2N Transilien", "Régio2N", None),
    "Z57400": ("Régio2N Transilien", "Régio2N", None),
    "Z59000": ("Régio2N", "Régio2N", None),
    # Autres matériels identifiables, composition à vérifier par version.
    "U53500": ("Citadis Dualis", "Tram-train", 4),
    "X73500": ("ATER", "X 73500", 1),
    "X72500": ("X TER", "X 72500", None),
    "Z21500": ("Z TER", "Z 21500", 3),
    "Z26500": ("TER 2N NG", "Z 26500", None),
    "Z50000": ("Francilien", "Z 50000", None),
    "Z20500": ("Z 2N", "Z 20500", None),
    "Z20900": ("Z 2N", "Z 20900", None),
    "Z22500": ("MI 2N", "Z 22500", 5),
}


def identifier_materiel(reference: str) -> dict[str, Any] | None:
    """Identifie une rame à partir d'une référence telle que 0KSRA-Z24595."""
    raw = str(reference).upper().replace(" ", "")
    match = re.search(r"([ZBXU])(\\d{5})([ML])?(?!\\w)", raw)
    if not match:
        return None
    prefix, number, suffix = match.groups()
    numeric = int(number)
    # Catalogue par séries : chaque tranche de cent numéros est indépendante.
    serie = f"{prefix}{numeric // 100 * 100:05d}"
    entry = MATERIELS_ROULANTS.get(serie)
    if entry is None:
        return None
    nom, famille, voitures = entry
    if famille == "Régiolis" and suffix in ("M", "L"):
        voitures = 4 if suffix == "M" else 6
    return {
        "reference": f"{prefix}{number}",
        "type": nom,
        "famille": famille,
        "voitures": voitures,
    }


def analyser_composition(elements: list) -> dict[str, Any]:
    """Calcule le nombre de rames et les voitures si toutes sont connues."""
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
    voitures = (
        sum(m["voitures"] for m in materiels)
        if len(rames) == len(elements)
        and all(m is not None and m["voitures"] is not None for m in materiels)
        else None
    )
    return {
        "train_units": len(elements),
        "train_composition": rames,
        "train_family": next(iter(familles)) if len(familles) == 1 and len(connus) == len(elements) else None,
        "train_type": next(iter(types)) if len(types) == 1 and len(connus) == len(elements) else None,
        "train_cars": voitures,
    }
