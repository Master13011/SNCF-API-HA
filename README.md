# 🚄 Intégration SNCF Trains pour Home Assistant

![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.5+-blue?logo=home-assistant)
![Custom Component](https://img.shields.io/badge/Custom%20Component-oui-orange)
![Licence MIT](https://img.shields.io/badge/Licence-MIT-green)

Intégration personnalisée Home Assistant pour suivre les horaires de trains SNCF entre deux gares, via l'API officielle [SNCF](https://www.digital.sncf.com/startup/api).  

Configurez facilement les villes et gares de départ / arrivée, ainsi qu’une plage horaire pour filtrer les résultats.

---

## 🔧 Installation

### 1. Via HACS (recommandé)
1. Aller dans **HACS > Intégrations > 3 points > Dépôt personnalisé**
2. Ajouter le dépôt : `https://github.com/Master13011/SNCF-API-HA`
3. Type de dépôt : `Intégration`
4. Rechercher `SNCF Trains` dans HACS, installer puis redémarrer Home Assistant.

### 2. Manuel (si pas HACS)
1. Télécharger le contenu du dépôt GitHub.
2. Copier le dossier `sncf_trains` dans `config/custom_components/`
3. Redémarrer Home Assistant.

---

## ⚙️ Configuration

Une fois redémarré :

1. Aller dans **Paramètres > Appareils et services > Ajouter une intégration**
2. Rechercher `SNCF Trains`
3. Suivre les étapes :
   - Clé API SNCF
   - Ville & gare de départ
   - Ville & gare d’arrivée
   - Plage horaire souhaitée

Vous pouvez configurer plusieurs trajets différents.

---

## 🧩 Options dynamiques (`options_flow`)

Une fois l'intégration ajoutée, vous pouvez ajuster dynamiquement plusieurs paramètres via l'interface sans devoir tout reconfigurer :

### Modifier les options :
1. Aller dans **Paramètres > Appareils et services**
2. Trouver votre intégration `SNCF Trains` > cliquez sur **Configurer**
3. Paramètres disponibles :
   - **Fréquence de mise à jour pendant la plage horaire**
   - **Fréquence de mise à jour en dehors de la plage horaire**
   - **Nombre de trains à afficher**
   - **Plage horaire personnalisée (début / fin)**

Les modifications sont prises en compte automatiquement, sans redémarrage nécessaire.

---

## 🔐 Clé API SNCF

Créer une clé sur [https://www.digital.sncf.com/startup/api](https://www.digital.sncf.com/startup/api) :

1. S'inscrire ou se connecter
2. Copier la clé et l'utiliser dans l'intégration

---

## ⚙️ Variables

- `update_interval` : fréquence de mise à jour pendant la plage horaire (2 minutes par défaut)

> ℹ️ L'option `update_interval` s'active automatiquement **2 heures avant** le début de la plage horaire définie.

- `outside_interval` : fréquence de mise à jour en dehors de la plage horaire (60 minutes par défaut)
- `train_count` : nombre maximum de départs à afficher
- `time_start` / `time_end` : plage horaire filtrant les départs à surveiller (ex. : 06:00 → 09:00)

---

## 📊 Capteurs créés

- `sensor.sncf_<nom_gare_dep>_to_<nom_gare_arr>` : nombre de trains à venir
- Attributs :
  - Liste des départs avec heure, retard éventuel, mode (TGV, TER, etc.)
  - Gares de départ et d’arrivée
  - Plage horaire configurée
  - Délai avant prochain départ

---

## 📸 Capture d'écran

<img width="354" height="453" alt="image" src="https://github.com/user-attachments/assets/15a88da4-fad0-46ca-8031-9864d3f48ed3" />


Résultat :  

<img width="608" height="262" alt="image" src="https://github.com/user-attachments/assets/39206e2a-8f44-4393-92fe-4196427b9bf9" />


Dashboard :

<img width="315" height="360" alt="image" src="https://github.com/user-attachments/assets/033fd0ce-ab61-4e54-83de-4bdb85d8aa58" />

---

## 🛠 Développement

Fonctionne avec Home Assistant `2024.5.0+`

Structure de base :
- `config_flow.py` : configuration UI
- `options_flow.py` : formulaire dynamique d'options utilisateur
- `sensor.py` : récupération des trajets
- `coordinator.py` : logique de rafraîchissement conditionnel
- `translations/fr.json` : support multilingue
- `manifest.json` : déclaration de l’intégration

---

## 🧑‍💻 Auteur

- Développé par [Master13011](https://github.com/Master13011)
- Contributions bienvenues via issues / PR sur [GitHub](https://github.com/Master13011/SNCF-API-HA)

---

## 📄 Licence

MIT - Utilisation libre, merci de mentionner l'auteur si réutilisé.
