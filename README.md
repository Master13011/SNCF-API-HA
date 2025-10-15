# 🚄 Intégration SNCF Trains pour Home Assistant

![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.5+-blue?logo=home-assistant)
![Custom Component](https://img.shields.io/badge/Custom%20Component-oui-orange)
![Licence MIT](https://img.shields.io/badge/Licence-MIT-green)

Suivez les horaires des trains SNCF entre deux gares dans Home Assistant, grâce à l’API officielle [SNCF](https://www.digital.sncf.com/startup/api).
Départ / arrivée, retards, durée, mode (TER…), tout est intégré dans une interface configurable et traduite.

Attention : ne prend pas en compte les trains supprimés

---

## 📦 Installation

### 1. Via HACS (recommandé)

> Nécessite HACS installé dans Home Assistant

1. Aller dans **HACS**
2. Cherchez directement : SNCF Trains
3. Installer puis redémarrer Home Assistant

### 2. Manuel (sans HACS)

1. Télécharger le contenu du dépôt
2. Copier le dossier `sncf_trains` dans `config/custom_components/`
3. Redémarrer Home Assistant

---

## ⚙️ Configuration

1. Aller dans **Paramètres → Appareils & services → Ajouter une intégration**
2. Rechercher **SNCF Trains**
3. Suivre les étapes :
   - Clé API SNCF
4. Ajouter un trajet
   - Ville et gare de départ
   - Ville et gare d’arrivée
   - Plage horaire à surveiller

Plusieurs trajets peuvent être configurés séparément.

---

## 🧩 Options dynamiques (Configurer)

Une fois configurée, cliquez sur **Configurer** pour ajuster :

- ⏱ Intervalle de mise à jour pendant la plage horaire
- 🕰 Intervalle hors plage


## 🧩 Options dynamiques pour un trajet (Reconfigurer un trajet)

- 🚆 Nombre de trains affichés
- 🕗 Heures de début et fin de surveillance

✅ Aucun redémarrage requis. Les modifications sont appliquées dynamiquement.

---

## 🔐 Clé API SNCF

Obtenez votre clé ici : [https://www.digital.sncf.com/startup/api](https://www.digital.sncf.com/startup/api)

1. Créez un compte ou connectez-vous
2. Générez une clé API gratuite
3. Utilisez-la lors de la configuration (limite de 5 000 requêtes par jour)

## 🧩 Options dynamiques (Reconfigurer)

Une fois configurée, cliquez sur **Reconfigurer** pour resaisir une nouvelle clé


---

## ⚙️ Variables prises en charge

| Nom                 | Description |
|----------------------|-------------|
| `update_interval`   | Intervalle de mise à jour **pendant** la plage horaire (défaut : 2 min) |
| `outside_interval`  | Intervalle **hors** plage horaire (défaut : 60 min) |
| `train_count`       | Nombre de trains à afficher |
| `time_start` / `time_end` | Heures de début et fin de la plage horaire (ex. : `06:00` → `09:00`) |

> 🕑 L’intervalle défini s’active automatiquement **2h avant** le début de plage.

---

## 📊 Capteurs créés

- `sensor.sncf_<gare_dep>_<gare_arr>`
- `sensor.sncf_train_X_<gare_dep>_<gare_arr>`
- `calendar.trains`
- `sensor.sncf_tous_les_trains_ligne_X`

### Attributs du capteur principal :

- Nombre de trajets
- Informations les inervalles


### Capteurs secondaires (enfants) pour chaque train :

- Heure de départ (`device_class: timestamp`)
- Heure d’arrivée
- Retard estimé
- Durée totale (`duration_minutes`)
- Mode, direction, numéro

---

## 📸 Aperçus

**Carte capteur :**

<img width="354" height="453" alt="sensor" src="https://github.com/user-attachments/assets/15a88da4-fad0-46ca-8031-9864d3f48ed3" />

**Détails du prochain train :**

<img width="608" height="262" alt="attributes" src="https://github.com/user-attachments/assets/39206e2a-8f44-4393-92fe-4196427b9bf9" />

**Dashboard Lovelace :**

<img width="315" height="360" alt="dashboard" src="https://github.com/user-attachments/assets/033fd0ce-ab61-4e54-83de-4bdb85d8aa58" />

---

## 🛠 Développement

Compatible avec Home Assistant `2025.8+`.

Structure :
- `__init__.py` : enregistrement de l’intégration
- `calendar.py` : calendrier
- `config_flow.py` : assistant UI de configuration
- `options_flow.py` : formulaire d’options dynamiques
- `sensor.py` : entités de capteurs
- `coordinator.py` : logique de récupération intelligente
- `translations/fr.json` : interface en français
- `manifest.json` : métadonnées et dépendances

---

## 👨‍💻 Auteur

Développé par [Master13011](https://github.com/Master13011)
Contributions bienvenues via **Pull Request** ou **Issues**

---

## 📄 Licence

Code open-source sous licence **MIT**
