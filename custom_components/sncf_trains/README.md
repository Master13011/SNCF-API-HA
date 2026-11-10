# Tests — Intégration SNCF Trains pour Home Assistant

Ce document décrit les tests automatisés de l'intégration `sncf_trains`.
Ils sont placés dans le dossier `tests/` et s'exécutent avec **pytest** et `pytest-homeassistant-custom-component`.

## Principes

- **Aucun accès réseau** : l'API SNCF (Navitia) et les services Gares & Connexions sont simulés avec `aioclient_mock` ou des `AsyncMock`.
- Les dates sont fixées dans les tests (ex. `20261109T070600`, ou `dt_util.now` remplacé) pour des résultats reproductibles.
- Une fixture `autouse` (`conftest.py`) active le chargement de l'intégration personnalisée dans chaque test.
- Dans `test_config_flow.py`, le setup de l'intégration est neutralisé (la dépendance `frontend` ne peut pas être chargée dans l'environnement de test).
- Exécution automatique via GitHub Actions (`.github/workflows/tests.yml`).

## Lancer les tests

```bash
pip install -r requirements.txt
pytest -q
```

## Contenu des tests

### `test_api.py` — client API (`SncfApiClient`)

| Domaine | Ce qui est vérifié |
|---|---|
| `encode_token` | Authentification Basic avec la clé comme identifiant et un mot de passe vide (`abc` → `YWJjOg==`). |
| `fetch_departures` | Requête sur un `stop_area` ou un `stop_point` (paramètres `count`, `data_freshness=realtime`, en-tête `Authorization`) ; identifiant inconnu → `ValueError` sans requête ; clé `departures` absente → liste vide. |
| `fetch_journeys` | Paramètres `from`, `to`, `datetime`, `count`, `datetime_represents=departure`, `data_freshness=realtime` ; rattachement des perturbations à chaque trajet ; clé `journeys` absente → liste vide. |
| `search_stations` | Paramètres `q` et `type[]=stop_point` ; clé `places` absente → liste vide. |
| Gestion des erreurs (les 3 méthodes) | HTTP 401 → `ConfigEntryAuthFailed` ; HTTP 429 → `RuntimeError` ; HTTP 500/503, erreur réseau ou timeout → `None`. |

### `test_config_flow.py` — assistant de configuration

| Test | Ce qui est vérifié |
|---|---|
| Cas nominal | Saisie d'une clé API valide : création de l'entrée « Trains SNCF » (`unique_id = sncf_trains`). |
| Clé invalide | Erreur `invalid_api_key` et retour au formulaire. |
| Instance unique | Une seconde configuration est abandonnée (`single_instance_allowed`). |
| Sous-entrée « trajet » | Parcours complet : ville de départ → gare de départ → ville d'arrivée → gare d'arrivée → plage horaire et nombre de trains ; titre, données et `unique_id` du trajet vérifiés. |
| Aucune gare | Erreur `no_stations` si aucune gare de départ ou d'arrivée n'est trouvée. |
| Doublon | Un trajet identique est refusé (`already_configured_as_entry`). |
| Options | Enregistrement des intervalles `update_interval` (5) et `outside_interval` (30). |

### `test_coordinator.py` — coordinateur

| Domaine | Ce qui est vérifié |
|---|---|
| Récupération | Trajets stockés par sous-entrée ; appel à l'API avec les bons arrêts et `count=10` ; intervalle de 2 minutes. |
| Filtrage | Seuls les trajets directs (`nb_transfers == 0`) sont conservés ; entrées invalides (`str`, `None`) ignorées. |
| Cas limites | Aucune sous-entrée → `{}` ; l'API renvoie `None` → `{}` après 3 tentatives ; données invalides → `{}` sans nouvelle tentative. |
| Nouvelles tentatives | Après `RuntimeError` (2 échecs puis succès), `TimeoutError` ou `ClientError` : nouvelle tentative avec pause de 2 s. |
| `_build_datetime_param` | Heure de début du jour même si la plage n'est pas passée, du lendemain sinon. |
| `_adjust_update_interval` | Intervalle rapide dans la plage horaire, dans l'heure qui la précède et pour une plage à cheval sur minuit ; intervalle lent en dehors. |

### `test_coordinator_enrichment.py` — enrichissement Gares & Connexions

| Domaine | Ce qui est vérifié |
|---|---|
| `_train_number` | Normalisation du numéro (zéros initiaux, espaces, entier, vide ou `None` → `"0"`). |
| `_matching_departure` | Rapprochement horaire à ±20 minutes ; gestion du suffixe UTC ; utilisation de l'arrêt de la gare choisie ; horaire théorique (et non réel) pour un train en retard ; heures inutilisables → pas de correspondance. |
| Voie | Voie lue dans l'horaire sans identifiant de circulation ; zéros initiaux ignorés. |
| Détail de circulation | Voies de départ et d'arrivée, composition, nombre d'unités et de voitures (source « catalogue »), famille et type de matériel, longueur ; requête bien formée (chemin, `isDeparture=true`, en-tête `x-environment: PROD`). |
| Robustesse | Une seule requête par circulation ; repli sur l'horaire si le détail est indisponible (404), vide ou en erreur réseau ; train à une autre heure non associé ; second candidat utilisé si le premier ne correspond pas ; numéro inconnu, erreur HTTP, format inattendu et éléments mal formés ignorés. |
| Gare d'embarquement | Enrichissement par gare (identifiants `stop_area` et `stop_point`) ; code UIC préfixé de zéros résolu ; origine administrative sans UIC ou trajet sans section de transport non enrichis ; l'échec de l'enrichissement ne casse pas la mise à jour ; aucun enrichissement sans trajet. |
| `_async_setup` | Le client API est construit avec la clé de l'entrée. |

### `test_helpers.py` et `test_helpers_parsing.py` — fonctions utilitaires

| Domaine | Ce qui est vérifié |
|---|---|
| Dates | `parse_datetime` (format Navitia, valeurs vides ou invalides → `None`) ; `format_time` (`09/11/2026 - 07:06`, sinon `N/A`) ; `get_duration` en minutes (0 si dates manquantes ou invalides). |
| `get_train_num` | Numéro lu sur le trajet, sur la section de transport (prioritaire sur la marche), via le champ `num`, ancien format, valeurs manquantes ou sections mal formées ignorées. |
| `attach_disruptions` | Liens vers les perturbations par `links`, `display_informations.links` ou clés alternatives (`impact_id`, `disruption_id`) ; pas de doublon ; liens inconnus ou non « disruption » ignorés ; entrées mal formées tolérées. |
| `disruption_summary` | Cause, effet et message de la perturbation principale ; cause de niveau supérieur prioritaire, puis cause de l'arrêt impacté ; valeurs `None` sans perturbation. |
| Composition | Une même rame répétée n'est comptée qu'une fois (6 voitures) ; deux rames distinctes totalisent 12 voitures. |

### `test_rolling_stock.py` — identification du matériel roulant

| Domaine | Ce qui est vérifié |
|---|---|
| `identifier_materiel` | Rame connue avec longueur fixe (`B85075` : Coradia Liner, Régiolis, 6 voitures) ; préfixe opérateur ignoré ; espaces et casse tolérés ; série sans longueur stable → pas de nombre de voitures ; variantes Régiolis `M`/`L` lues seulement si explicites ; familles TGV (Atlantique, Duplex, Réseau, M) ; locomotive sans nombre de voitures ; références inconnues ou invalides → `None`. |
| `analyser_composition` | Rame seule ; rames couplées du même type additionnées ; rames de types différents sans famille ni type uniques ; une rame inconnue ou sans longueur rend le total inconnu ; locomotive non comptée comme rame ; élément sans numéro d'affectation ou invalide ignoré. |

### `test_sensor.py` et `test_sensor_attributes.py` — capteurs

| Domaine | Ce qui est vérifié |
|---|---|
| Création | Autant de capteurs « train » que configuré, même avec moins de trajets disponibles ; un capteur « ligne » ; pas d'erreur sans trajet ; un capteur vide est rempli à la mise à jour suivante. |
| `get_transport_section` | Section de transport trouvée parmi les sections de marche ; repli sur la première section ; trajet mal formé → `{}`. |
| `SncfJourneySensor` | Nombre de trajets configurés, attributs d'intervalles, appareil ; suit le coordinateur. |
| `SncfTrainSensor` | Nom, `unique_id` et appareil ; état = heure de départ théorique ; attributs d'un train à l'heure (horaires, retard, durée, arrêts, direction, modes, numéro) et en retard (10 min, statut) ; `N/A` pour les données d'enrichissement inconnues ; voies, composition et matériel exposés ; résumé de perturbation ; capteur vidé si le trajet disparaît ; données de sous-entrée manquantes tolérées. |
| `SncfAllTrainsLineSensor` | Identité (même appareil que les trains) ; agrégation des horaires et retards (`"0; 5"`) ; `has_delay` ; ligne sans trajet ; trajets mal formés ignorés ; suit le coordinateur. |

### `test_calendar.py` — calendrier

| Domaine | Ce qui est vérifié |
|---|---|
| Entité | `unique_id`, nom, appareil. |
| Conversion | Trajet → événement (résumé `Départ → Arrivée`, lieu, uid, numéro de train, horaires) ; trajet en retard signalé dans le résumé (`- RETARD (10min)`) ; uid de repli ; numéro de train non numérique → `None` ; trajets invalides ignorés ; nombre d'événements limité par `train_count` ; sous-entrées inconnues ignorées. |
| Événement courant | Le plus proche de maintenant, avec ses attributs ; mis à jour à chaque rafraîchissement ; masqué si le coordinateur est en échec ; `async_get_events` renvoie tous les trajets, ou rien en cas d'échec. |

### `test_diagnostics.py` — diagnostics

| Test | Ce qui est vérifié |
|---|---|
| Confidentialité | La clé API est masquée (`REDACTED`) dans `data` et `options` ; les autres valeurs restent visibles. |
| Coordinateur | Disponibilité, dernière mise à jour, intervalles, nombre de sous-entrées. |
| Détails | Informations de sous-entrée et de trajet (numéro de train, horaires, statut, sections). |
| Limites | Au plus 10 trajets détaillés, mais tous sont comptés. |
| Données invalides | Trajets et sections invalides signalés ; sections non listées traitées comme vides ; sous-entrée sans donnée ou avec données invalides ; coordinateur absent (`Coordinator non disponible`). |

### `test_init.py` — installation et migration

| Domaine | Ce qui est vérifié |
|---|---|
| Carte Lovelace | Enregistrement de la carte quand Home Assistant est démarré ; report jusqu'à l'événement de démarrage sinon ; le fichier de la carte existe. |
| Setup / unload / reload | Coordinateur stocké et plateformes transmises ; échec du premier rafraîchissement propagé (`ConfigEntryNotReady`) ; résultat du déchargement des plateformes renvoyé ; rechargement de l'entrée. |
| Migration (1.1 → 1.2) | Ancien trajet converti en sous-entrée (titre, `unique_id`, données) ; valeurs par défaut et identifiants utilisés comme noms ; réglages lus dans `data` si absents des options ; clé API déplacée des options vers `data` sans écraser l'existante ; aucune sous-entrée créée sans ancien trajet ; sous-entrées existantes conservées ; migration idempotente ; entrée à jour inchangée ; version plus récente refusée. |
