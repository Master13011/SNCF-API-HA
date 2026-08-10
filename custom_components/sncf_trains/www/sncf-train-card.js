// Ajouter au registre des cartes personnalisées
globalThis.customCards ||= []
globalThis.customCards.push({
  type: 'sncf-train-card',
  name: 'SNCF Train Card',
  description: 'Carte personnalisée animée pour afficher les trains SNCF en temps réel',
  preview: true,
  configurable: true
});

class SncfTrainCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this.updateInterval = null;
    this.lastTrainSignature = null;
    this._lastRenderTime = 0;
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Permet de définir la configuration de la carte, avec validation et gestion des changements de device_id pour forcer une mise à jour immédiate
   * @param {Object} config - La configuration de la carte, qui doit inclure au minimum un device_id valide pour fonctionner correctement, et peut inclure d'autres paramètres pour personnaliser l'affichage
   * @throws {Error} Si le device_id n'est pas défini, une erreur est levée pour informer l'utilisateur de la nécessité de fournir cette information essentielle
   */
  setConfig(config) {
    if (!config.device_id) {
      throw new Error('You need to define device_id');
    }

    // Normaliser device_id en tableau (rétrocompatibilité)
    let normalizedDeviceId = config.device_id;
    if (typeof normalizedDeviceId === 'string') {
      normalizedDeviceId = [normalizedDeviceId];
    } else if (!Array.isArray(normalizedDeviceId)) {
      throw new Error('device_id must be a string or an array of strings');
    }

    // Vérifier qu'il y a au moins un device_id non-vide
    if (!normalizedDeviceId.length || !normalizedDeviceId.some(id => id)) {
      throw new Error('You need to define at least one valid device_id');
    }

    const previousDeviceId = this.config ? this.config.device_id : null;
    const deviceIdChanged = previousDeviceId && JSON.stringify(previousDeviceId) !== JSON.stringify(normalizedDeviceId);

    // Créer une copie de la config avec le device_id normalisé
    this.config = { ...config, device_id: normalizedDeviceId };

    // Forcer la mise à jour immédiate si device_id a changé
    if (deviceIdChanged) {
      this.stopUpdateTimer();
      this.startUpdateTimer();
    }

    // Toujours forcer un nouveau rendu
    this.render();
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Fournit la configuration du formulaire pour l'éditeur de Lovelace, avec des labels et des aides personnalisés
   */
  static getConfigForm() {
    return {
      schema: [
        {
          name: "device_id",
          required: true,
          selector: {
            device: {
              multiple: true,
              filter: {
                integration: "sncf_trains"
              }
            }
          }
        },
        {
          name: "title",
          selector: {text: {}},
        },
        {
          name: "train_lines",
          selector: {
            number: {
              min: 1,
              max: 10,
              step: 1,
            },
          },
        },
        {
          name: "animation_duration",
          selector: {
            number: {
              min: 0,
              max: 100,
              step: 1,
            },
          },
        },
        {
          name: "update_interval",
          selector: {
            number: {
              min: 5000,
              step: 1000,
            },
          },
        },
        {
          type: "grid",
          name: "",
          column_min_width: "150px",
          schema: [
            {
              name: "train_emoji_axial_symmetry",
              selector: {boolean: {}},
            },
            {
              name: "train_emoji",
              selector: {
                icon: {},
              },
            },
            {
              name: "show_departure_station",
              selector: {boolean: {}},
            },
            {
              name: "departure_station_emoji",
              selector: {
                icon: {},
              },
            },
            {
              name: "show_arrival_station",
              selector: {boolean: {}},
            },
            {
              name: "arrival_station_emoji",
              selector: {
                icon: {},
              },
            },
          ]
        },
      ],
      computeLabel: (schema) => {
        const labels = {
          device_id: "IDs des Devices (obligatoire - tableau de devices)",
          title: "Titre de la carte",
          train_emoji: "Emoji du train",
          train_lines: "Nombre de trains à afficher",
          animation_duration: "Durée d'animation (minutes)",
          update_interval: "Intervalle de mise à jour (ms)",
          departure_station_emoji: "Emoji de la gare de départ",
          arrival_station_emoji: "Emoji de la gare d'arrivée",
          show_departure_station: "Afficher les informations de départ",
          show_arrival_station: "Afficher les informations d'arrivée",
          train_emoji_axial_symmetry: "Symétrie axiale du train",
        };
        return labels[schema.name] || undefined;
      },
      computeHelper: (schema) => {
        const helpers = {
          device_id: "Les identifiants uniques des devices SNCF à afficher (tableau de devices)",
          title: "Le titre affiché en haut de la carte",
          train_emoji: "L'emoji représentant le train",
          train_lines: "Le nombre de trains à afficher (1-10)",
          animation_duration: "Nombre de minutes avant le départ pour que le train apparaisse",
          update_interval: "Fréquence de rafraîchissement en millisecondes (ex: 30000 pour 30s)",
          departure_station_emoji: "L'emoji pour la gare de départ",
          arrival_station_emoji: "L'emoji pour la gare d'arrivée",
          show_departure_station: "Affiche ou masque la gare de départ",
          show_arrival_station: "Affiche ou masque la gare d'arrivée",
          train_emoji_axial_symmetry: "Retourner l'emoji du train horizontalement",
        };
        return helpers[schema.name] || undefined;
      },
    };
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Fournit une configuration par défaut pour le mode aperçu dans l'éditeur de Lovelace
   */
  static getStubConfig() {
    return {
      device_id: ['', ''],
      title: 'Trains SNCF',
      train_lines: 5,
      animation_duration: 30,
      update_interval: 30000,
      train_emoji_axial_symmetry: true,
      train_emoji: '🚅',
      show_departure_station: true,
      departure_station_emoji: '',
      show_arrival_station: true,
      arrival_station_emoji: '🚉',
    };
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Permet de recevoir l'objet Home Assistant et de déclencher une vérification des mises à jour des trains pour éviter les rendus inutiles
   * @param {Object} hass - L'objet Home Assistant fourni par le système, utilisé pour accéder aux états et aux services, et pour déclencher des mises à jour de la carte lorsque les données des trains changent
   */
  set hass(hass) {
    const previousHass = this._hass;
    this._hass = hass;

    // Vérifier si les données des trains ont changé
    if (this.config && previousHass) {
      this.checkForTrainUpdates(previousHass, hass);
    } else {
      this.render();
    }
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Démarre un timer pour forcer des mises à jour régulières, ce qui est nécessaire pour capturer les changements de données en temps réel
   */
  connectedCallback() {
    this.startUpdateTimer();
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Arrête le timer de mise à jour pour éviter les fuites de mémoire lorsque la carte est retirée du DOM
   */
  disconnectedCallback() {
    this.stopUpdateTimer();
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Calcule la taille de la carte en fonction du nombre de lignes de train à afficher, avec une taille minimale pour éviter les problèmes d'affichage
   */
  getCardSize() {
    return Math.max(3, this.config.train_lines + 1);
  }

  /**
   * Vérifie si les données des trains ont changé en comparant une signature des données actuelles avec la dernière signature connue, et ne fait un rendu que si nécessaire pour optimiser les performances
   * @param {Object} previousHass - L'objet Home Assistant précédent pour comparer les données
   * @param {Object} currentHass - L'objet Home Assistant actuel pour récupérer les données fraîches
   */
  async checkForTrainUpdates(previousHass, currentHass) {
    try {
      // Récupérer les entités actuelles
      const currentTrains = await this.getTrainEntities();

      // Créer une signature des données actuelles
      const currentSignature = this.createTrainSignature(currentTrains);

      // Comparer avec la signature précédente
      if (currentSignature !== this.lastTrainSignature) {
        this.lastTrainSignature = currentSignature;
        this.render();
      }
    } catch (error) {
      // En cas d'erreur, faire un rendu quand même
      console.error(error);
      this.render();
    }
  }

  /**
   * Crée une signature unique pour les données des trains en concaténant les informations clés de chaque train, ce qui permet de détecter facilement les changements sans faire un rendu complet à chaque fois
   * @param {Array} trains - Un tableau d'entités de train
   * @returns {string} Une chaîne de caractères représentant la signature des données des trains
   */
  createTrainSignature(trains) {
    return trains.map(train =>
      `${train.entity_id}:${train.attributes.departure_time}:${train.attributes.delay_minutes || 0}:${train.attributes.has_delay || false}`
    ).join('|');
  }

  /**
   * Démarre un timer qui force un rendu de la carte à intervalles réguliers, ce qui est nécessaire pour capturer les changements de données en temps réel, surtout pour les données de train qui peuvent changer fréquemment
   */
  startUpdateTimer() {
    this.stopUpdateTimer();
    this.updateInterval = setInterval(async () => {
      if (this._hass) {
        // Force un nouveau rendu à intervalles réguliers pour capturer les changements
        this._lastRenderTime = 0; // Reset du throttle
        await this.render();
      }
    }, this.config.update_interval);
  }

  /**
   * Arrête le timer de mise à jour pour éviter les fuites de mémoire lorsque la carte est retirée du DOM ou lorsque le device_id change, ce qui est important pour maintenir les performances et éviter les rendus inutiles
   */
  stopUpdateTimer() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  /**
   * Récupère les entités de train associées aux device_id configurés en utilisant l'API WebSocket de Home Assistant pour obtenir des données fraîches, filtre les trains qui ne sont pas encore passés, et trie les résultats par heure de départ pour n'afficher que les trains à venir, ce qui garantit que les informations affichées sont toujours à jour et pertinentes pour l'utilisateur
   * @returns {Promise<Array>} Un tableau d'entités de train avec des données fraîches, fusionnées de tous les devices et triées par date d'arrivée
   */
  async getTrainEntities() {
    if (!this._hass || !this.config.device_id) return [];

    try {
      // Utiliser l'API Home Assistant pour récupérer toutes les entités
      const allEntityRegistry = await this._hass.callWS({
        type: 'config/entity_registry/list'
      });

      // Récupérer les entités pour tous les device_id
      const allTrainEntities = [];

      for (const deviceId of this.config.device_id) {
        if (!deviceId) continue;

        // Filtrer les entités par device_id
        const deviceEntities = allEntityRegistry.filter(entityInfo =>
          entityInfo.device_id === deviceId
        );

        if (!deviceEntities || deviceEntities.length === 0) {
          console.warn(`⚠️ Aucune entité trouvée pour le device_id: ${deviceId}`);
          continue;
        }

        // Récupérer les états des entités train trouvées avec données fraîches
        const trainEntities = deviceEntities
          .filter(entityInfo => entityInfo.entity_id.includes('train'))
          .map(entityInfo => {
            // Forcer la récupération de l'état frais
            return this._hass.states[entityInfo.entity_id];
          })
          .filter(entity => entity?.attributes?.departure_time);

        allTrainEntities.push(...trainEntities);
      }

      // Source - https://stackoverflow.com/a/1214753
      // Posted by Kip, modified by community. See post 'Timeline' for change history
      // Retrieved 2026-05-15, License - CC BY-SA 4.0
      const addMinutes = (date, minutes) => {
        return new Date(date.getTime() + minutes*60000);
      }

      // Filtrer les trains qui ne sont pas encore passés
      const currentTime = new Date();
      const upcomingTrains = allTrainEntities.filter(entity => {
        // TODO : paramétrer le temps d'affichage max d'un train arrivé en gare
        const arrivalTime = addMinutes(this.parseTime(entity.attributes.arrival_time), 30);
        return arrivalTime >= currentTime;
      });

      return upcomingTrains
        .sort((a, b) => {
          const aTime = this.parseTime(a.attributes.arrival_time);
          const bTime = this.parseTime(b.attributes.arrival_time);
          return aTime - bTime;
        })
        .slice(0, this.config.train_lines);

    } catch (error) {
      console.error('❌ Erreur lors de la récupération via API:', error);
      return [];
    }
  }

  /**
   * Parse une chaîne de temps au format spécifique de la SNCF (ex: "19/11/2025 - 08:20") et retourne un objet Date, ou une date par défaut si le format est invalide ou si la chaîne est vide, ce qui permet de gérer correctement les données de temps fournies par les entités de train et d'éviter les erreurs d'affichage
   * @param {string} departureTime - La chaîne de temps à parser, qui peut être au format SNCF ou un format standard reconnu par JavaScript
   * @returns {Date} Un objet Date représentant le temps de départ, ou une date par défaut si le parsing échoue
   */
  parseTime(departureTime) {
    if (!departureTime) {
      return new Date(0);
    }

    // Format SNCF: "19/11/2025 - 08:20"
    if (departureTime.includes('/') && departureTime.includes(' - ')) {
      const parts = departureTime.split(' - ');
      if (parts.length === 2) {
        const datePart = parts[0]; // "19/11/2025"
        const timePart = parts[1]; // "08:20"

        const dateComponents = datePart.split('/');
        if (dateComponents.length === 3) {
          const day = Number.parseInt(dateComponents[0]);
          const month = Number.parseInt(dateComponents[1]) - 1; // Mois 0-indexé
          const year = Number.parseInt(dateComponents[2]);

          const timeComponents = timePart.split(':');
          if (timeComponents.length === 2) {
            const hour = Number.parseInt(timeComponents[0]);
            const minute = Number.parseInt(timeComponents[1]);

            return new Date(year, month, day, hour, minute);
          }
        }
      }
    }

    // Fallback vers Date classique
    return new Date(departureTime);
  }

  /**
   * Calcule la position du train sur la barre de progression en fonction de l'heure actuelle et de l'heure de départ, en affichant le train 30 minutes avant le départ et en le faisant avancer vers la droite à mesure que l'heure de départ approche, ce qui crée une animation visuelle intuitive pour les utilisateurs afin de suivre l'approche du train vers la gare, et retourne une position en pourcentage (0% = train à gauche, 100% = train arrivé) ou une valeur négative pour indiquer que le train n'est pas encore visible, ce qui permet de gérer l'affichage du train de manière dynamique en fonction du temps restant avant le départ
   * @param {object} trainAttributes - Les attributs du train, qui doivent inclure au minimum une heure de départ valide pour que le calcul fonctionne correctement, et peuvent inclure d'autres informations pour personnaliser l'affichage
   * @returns {number} Un nombre représentant la position du train en pourcentage (0-100) ou une valeur négative si le train n'est pas encore visible
   */
  calculateTrainPosition(trainAttributes) {
    if (!trainAttributes.departure_time || !trainAttributes.arrival_time) {
      return -10;
    }

    const departure = this.parseTime(trainAttributes.departure_time);
    const arrival = this.parseTime(trainAttributes.arrival_time);
    const travelTime = (arrival - departure) / (1000 * 60);

    if (Number.isNaN(departure.getTime()) || Number.isNaN(arrival.getTime()) || travelTime < 0) {
      return -10;
    }

    const now = new Date();
    const diffMinutes = (arrival - now) / (1000 * 60);

    if (diffMinutes > travelTime) {
      // TODO : tester et s'assurer de la véracité / nom du param animation_duration
      if (this.config.animation_duration === 0 || this.config.animation_duration > diffMinutes - travelTime) {
        // Train apparaît X minutes avant l'heure
        return 0;
      }
      // Hors de la barre
      return -10;
    }
    if (diffMinutes <= 0) {
      // Arrivé à la gare
      return 100;
    }

    // Position sur la barre (0% = gauche, 100% = droite)
    return ((travelTime - diffMinutes) / travelTime) * 100;
  }

  /**
   * Formate une chaîne de temps en une heure lisible au format français (ex: "08:20"), ou retourne "N/A" si la chaîne est vide, ou "Format invalide" si le parsing échoue, ce qui permet d'afficher les heures de départ et d'arrivée de manière claire et compréhensible pour les utilisateurs, tout en gérant les cas où les données de temps peuvent être manquantes ou mal formatées
   * @param {string} timeString - La chaîne de temps à formater, qui doit être au format reconnu par la méthode parseTime
   * @returns {string} Une chaîne représentant l'heure formatée ou un message d'erreur si le format est invalide
   */
  formatTime(timeString) {
    if (!timeString) {
      return 'N/A';
    }

    const time = this.parseTime(timeString);

    if (Number.isNaN(time.getTime())) {
      return 'Format invalide';
    }

    return time.toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  /**
   * Calcule l'heure d'arrivée réelle en ajoutant les minutes de retard à l'heure de départ prévue, et retourne une chaîne formatée de l'heure d'arrivée réelle, ou null si les données nécessaires sont manquantes ou si le train n'a pas de retard.
   * @param departureTime - L'heure de départ
   * @param delayMinutes - Le temps de retard en minutes
   * @returns {string} Une chaîne représentant l'heure avec retard formatée ou null
   */
  // TODO : tester si encore utile ?
  calculateRealArrivalTime(departureTime, delayMinutes) {
    if (!departureTime || !delayMinutes || delayMinutes === 0) {
      return null;
    }

    const originalTime = this.parseTime(departureTime);
    const realTime = new Date(originalTime.getTime() + (delayMinutes * 60000)); // Ajouter les minutes de retard

    return realTime.toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  /**
   * Calcule la couleur du train en fonction du retard
   * @param {number} delayMinutes - Le nombre de minutes de retard
   * @param {boolean} hasDelay - Indique si le train a du retard ou non
   * @returns {string} La couleur correspondante
   */
  getTrainColor(delayMinutes, hasDelay) {
    if (!hasDelay || delayMinutes === 0) return '#4caf50'; // Vert à l'heure
    return '#f44336'; // Rouge en retard (peu importe le nombre de minutes)
  }

  /**
   * <b><u>Méthode héritée</u></b><br>
   * Génération du rendu de l'ensemble de la carte, incluant le css et l'html
   */
  async render() {
    if (!this._hass || !this.config) {
      return;
    }

    // Éviter les rendus trop fréquents (max 1 par seconde)
    const now = Date.now();
    if (now - this._lastRenderTime < 1000) {
      return;
    }
    this._lastRenderTime = now;

    const trains = await this.getTrainEntities();

    if (trains.length === 0) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div class="card-content">
            <div class="error">Aucun train trouvé pour ce device. Vérifiez la configuration.</div>
          </div>
        </ha-card>
      `;
      return;
    }

    this.shadowRoot.innerHTML = `
      ${this.renderCss()}

      <ha-card>
        <div class="train-card">
          <div class="train-header">
            <div>${this.config.title}</div>
          </div>

          ${this.renderTrainLines(trains)}

        </div>
      </ha-card>
    `;
  }

  /**
   * Rendu des icônes en fonction de la configuration, en vérifiant si l'icône est un emoji simple ou une icône HA (mdi:, fa:, ic:, ...), et en retournant le HTML approprié pour chaque cas.
   * @param icone - La chaîne de caractères représentant l'icône configurée, qui peut être un emoji simple ou une icône HA avec un préfixe spécifique, et qui doit être traitée différemment pour s'assurer qu'elle s'affiche correctement dans la carte
   * @return {string} Une chaîne HTML représentant l'icône à afficher, soit en utilisant la balise <ha-icon> pour les icônes HA, soit en affichant directement l'emoji pour les emojis simples, ce qui permet de gérer une grande variété d'icônes de manière flexible et personnalisable
   */
  renderIcone(icone) {
    if (icone?.includes(':')) {
      return `<ha-icon icon="${icone}" class="mdi-icon"></ha-icon>`;
    }
    return icone;
  }

  /**
   * Rendu des lignes de train en fonction des données fournies, en calculant la position de chaque train sur la barre de progression, en affichant les informations de départ et d'arrivée selon la configuration, et en appliquant des styles différents pour les trains en retards.
   * @param {Array} trains - Un tableau d'entités de train à afficher, avec leurs attributs contenant les informations nécessaires pour le rendu
   * @returns {string} Une chaîne HTML représentant la section complète du train
   */
  renderTrainLines(trains) {
    return trains.map((train, index) => {
      const TA = train.attributes;
      const position = this.calculateTrainPosition(TA);
      const delayMinutes = TA.delay_minutes || 0;
      const hasDelay = TA.has_delay || false;
      const isRunning = this.parseTime(TA.departure_time) < new Date() && new Date() < this.parseTime(TA.arrival_time)
      const isArrived = new Date() > this.parseTime(TA.arrival_time)
      const trainColor = this.getTrainColor(delayMinutes, hasDelay);

      const theme = isArrived ? 'arrived' : hasDelay ? 'delayed' : isRunning ? 'running' : '';
      return `
        <div class="train-line">
          ${this.config.show_departure_station ? this.renderDeparture(TA) : ''}

          <div class="train-track ${theme}">
            ${ position >= 0 ?
            `<div class="train-emoji train-emoji-axial-symmetry-${this.config.train_emoji_axial_symmetry}"
              style="left: ${position}%; color: ${trainColor};">
                ${this.renderIcone(this.config.train_emoji)}
            </div>` : ''
            }
          </div>

          ${this.config.show_arrival_station ? this.renderArrival(TA) : ''}
        </div>
      `;
    }).join('');
  }

  /**
   * Rendu de la section de départ pour un train donné, en affichant l'heure de départ prévue, l'heure de départ réelle si le train a du retard.
   * @param {object} trainAttributes - Les attributs du train
   * @returns {string} Une chaîne HTML représentant la section de départ du train
   */
  renderDeparture(trainAttributes) {
    const hasDelay = trainAttributes.has_delay || false;
    const isGone = new Date() > this.parseTime(trainAttributes.departure_time)
    const delayMinutes = trainAttributes.delay_minutes || 0;
    const departureTime = this.formatTime(trainAttributes.base_departure_time);
    const realDepartureTime = this.formatTime(trainAttributes.departure_time);

    return `
      <div class="station">
        <div class="station-info">
          <div class="arrival-time-container">
            ${hasDelay && realDepartureTime ? `
              <div class="arrival-time original-time">${departureTime}</div>
              <div class="arrival-time real-time">${realDepartureTime}</div>
            ` : `
              <div class="arrival-time">${departureTime}</div>
            `}
          </div>
          <div class="delay-info ${hasDelay ? 'delay' : 'on-time'}">
            ${hasDelay ? `+${delayMinutes}min` : isGone ? 'Parti' : 'À l\'heure'}
          </div>
        </div>
        <div class="station-emoji">${this.renderIcone(this.config.departure_station_emoji)}</div>
      </div>
    `
  }

  /**
   * Rendu de la section d'arrivée pour un train donné, en affichant l'heure d'arrivée prévue, l'heure d'arrivée réelle si le train a du retard.
   * @param {object} trainAttributes - Les attributs du train
   * @returns {string} Une chaîne HTML représentant la section d'arrivée du train
   */
  renderArrival(trainAttributes) {
    const hasDelay = trainAttributes.has_delay || false;
    const isArrived = new Date() > this.parseTime(trainAttributes.arrival_time)
    const delayMinutes = trainAttributes.delay_minutes || 0;
    const arrivalTime = this.formatTime(trainAttributes.base_arrival_time);
    const realArrivalTime = this.formatTime(trainAttributes.arrival_time);

    return `
      <div class="station">
        <div class="station-emoji">${this.renderIcone(this.config.arrival_station_emoji)}</div>
        <div class="station-info">
          <div class="arrival-time-container">
            ${hasDelay && realArrivalTime ? `
              <div class="arrival-time original-time">${arrivalTime}</div>
              <div class="arrival-time real-time">${realArrivalTime}</div>
            ` : `
              <div class="arrival-time">${arrivalTime}</div>
            `}
          </div>
          <div class="delay-info ${hasDelay ? 'delay' : 'on-time'}">
            ${hasDelay ? `+${delayMinutes}min` : isArrived ? 'Arrivé' : 'À l\'heure'}
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Rendu du CSS pour la carte, en définissant les styles de base pour la carte, les lignes de train, les barres de progression, les emojis, et les informations de station
   * @return {string} Une chaîne HTML contenant les styles CSS pour la carte.
   */
  renderCss() {
    return `
      <style>
        ha-card {
          padding: 16px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
          overflow: hidden;
        }

        .train-card {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .train-header {
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 1.4em;
          font-weight: 600;
          color: var(--primary-color, #00539c);
          border-bottom: 2px solid var(--divider-color, #e0e0e0);
          padding-bottom: 10px;
        }

        .train-line {
          display: flex;
          align-items: center;
          margin-bottom: 24px;
          position: relative;
          min-height: 60px;
        }

        .train-track {
          position: relative;
          flex: 1;
          height: 8px;
          background: linear-gradient(90deg, #ddd 0%, #bbb 50%, #ddd 100%);
          border-radius: 4px;
          margin: 0 16px;
          overflow: visible;
          box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
          transition: background 0.3s ease;
        }

        .train-track.delayed {
          background: linear-gradient(90deg, #ffcdd2 0%, #e57373 50%, #ffcdd2 100%);
          box-shadow: inset 0 2px 4px rgba(244,67,54,0.3);
        }

        .train-track.running {
          background: linear-gradient(90deg, #d2cdff 0%, #7373e5 50%, #d2cdff 100%);
          box-shadow: inset 0 2px 4px rgba(54,67,244,0.3);
        }

        .train-track.arrived {
          background: linear-gradient(90deg, #cdffd2 0%, #73e573 50%, #cdffd2 100%);
          box-shadow: inset 0 2px 4px rgba(67,244,54,0.3);
        }

        .train-track::before {
          content: '';
          position: absolute;
          top: 50%;
          left: 0;
          right: 0;
          height: 2px;
          background: repeating-linear-gradient(
          90deg,
          #999 0px,
          #999 10px,
          transparent 10px,
          transparent 20px
          );
          transform: translateY(-50%);
          transition: background 0.3s ease;
        }

        .train-track.delayed::before {
          background: repeating-linear-gradient(
          90deg,
          #d32f2f 0px,
          #d32f2f 10px,
          transparent 10px,
          transparent 20px
          );
        }

        .train-track.running::before {
          background: repeating-linear-gradient(
          90deg,
          #2f2fd3 0px,
          #2f2fd3 10px,
          transparent 10px,
          transparent 20px
          );
        }

        .train-track.arrived::before {
          background: repeating-linear-gradient(
          90deg,
          #2fd32f 0px,
          #2fd32f 10px,
          transparent 10px,
          transparent 20px
          );
        }

        .train-emoji {
          position: absolute;
          top: -37px;
          transform: translateX(-50%);
          font-size: 2em;
          transition: left 0.5s ease-in-out;
          z-index: 10;
          filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));
        }

        .train-emoji-axial-symmetry-true {
          transform: translateX(-50%) scaleX(-1);
        }

        .station {
          display: flex;
          flex-direction: row;
          align-items: center;
          gap: 8px;
        }

        .station-emoji {
          font-size: 1.8em;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
        }

        .station-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .arrival-time {
          font-size: 1.1em;
          font-weight: 600;
          color: var(--primary-color, #00539c);
        }

        .arrival-time-container {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .original-time {
          text-decoration: line-through;
          color: var(--secondary-text-color, #666);
          font-size: 0.9em;
        }

        .real-time {
          color: var(--error-color, #f44336);
          font-weight: 700;
        }

        .delay-info {
          font-size: 0.8em;
          font-weight: 600;
          margin-top: 2px;
        }

        .on-time {
          color: var(--success-color, #4caf50);
        }

        .error {
          color: var(--error-color, #f44336);
          text-align: center;
          padding: 20px;
          font-weight: 500;
        }
      </style>
    `;
  }

}

// Définir l'élément custom
customElements.define('sncf-train-card', SncfTrainCard);