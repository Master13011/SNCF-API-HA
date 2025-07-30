# 🚄 Intégration SNCF Trains pour Home Assistant - BETA

![Home Assistant](https://img.shields.io/badge/Home--Assistant-2024.5+-blue?logo=home-assistant)
![Custom Component](https://img.shields.io/badge/Custom%20Component-oui-orange)
![Licence MIT](https://img.shields.io/badge/Licence-MIT-green)

Intégration personnalisée Home Assistant pour suivre les horaires de trains SNCF entre deux gares, via l'API officielle [SNCF](https://www.digital.sncf.com/startup/api).  
Configurez facilement les villes et gares de départ / arrivée, ainsi qu’une plage horaire pour filtrer les résultats.

---

## 🔧 Installation

### 1. Via HACS (recommandé)
1. Aller dans **HACS > Intégrations > 3 points > Dépôt personnalisé**
2. Ajouter le dépôt :  https://github.com/Master13011/SNCF-API-HA
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
- Tranche horaire souhaitée

Vous pouvez configurer plusieurs trajets différents.

---

## 🔐 Clé API SNCF

Créer une clé sur [https://www.digital.sncf.com/startup/api](https://www.digital.sncf.com/startup/api) :

1. S'inscrire ou se connecter
2. Aller dans **Mes API > Navitia**
3. Créer une nouvelle clé
4. Copier la clé et l'utiliser dans l'intégration

---

## 📊 Capteurs créés

- `sensor.sncf_<nom_gare_dep>_to_<nom_gare_arr>` : nombre de trains à venir
- Attributs :
- Liste des départs avec heure, retard éventuel, mode (TGV, TER, etc.)
- Gares de départ et d’arrivée
- Plage horaire configurée

---

## 📸 Capture d'écran

<img width="329" height="206" alt="image" src="https://github.com/user-attachments/assets/5488ee4b-fcd5-4e21-93e9-56dfbe47c08c" />

<img width="515" height="679" alt="image" src="https://github.com/user-attachments/assets/0331aa95-93a7-495b-a392-138080b08361" />


---

## 🛠 Développement

Fonctionne avec Home Assistant `2024.5.0+`

Structure de base :
- `config_flow.py` : configuration UI
- `sensor.py` : récupération des trajets
- `translations/fr.json` : support multilingue
- `manifest.json` : déclaration de l’intégration

---

## 🧑‍💻 Auteur

- Développé par [Master13011](https://github.com/Master13011)
- Contributions bienvenues via issues / PR sur [GitHub](https://github.com/Master13011/SNCF-API-HA)

---

## 📄 Licence

MIT - Utilisation libre, merci de mentionner l'auteur si réutilisé.
