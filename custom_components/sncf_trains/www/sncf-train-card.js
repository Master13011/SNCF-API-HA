// SNCF Train Card V3.5.1
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'sncf-train-card',
  name: 'SNCF Train Card',
  preview: true,
  description: 'Version intégrale - Radar, Animation temps réel et Éditeur visuel.'
});

// --- ÉDITEUR VISUEL (CODE COMPLET) ---
class SncfTrainCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    this._config = { ...config };
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  render() {
    if (!this._config) return;

    this.shadowRoot.innerHTML = `
      <div class="card-config">
        <div class="field">
          <label>Titre de la carte</label>
          <input type="text" id="title" value="${this._config.title || 'Trains SNCF'}">
        </div>
        
        <div class="field">
          <label>Device ID (Requis)</label>
          <input type="text" id="device_id" value="${this._config.device_id || ''}" placeholder="Ex: 87dc6f059b...">
        </div>

        <div class="field-row">
          <div class="field">
            <label>Nombre de trains</label>
            <input type="number" id="train_lines" min="1" max="10" value="${this._config.train_lines !== undefined ? this._config.train_lines : 3}">
          </div>
          <div class="field">
            <label>Durée animation (min)</label>
            <input type="number" id="animation_duration" value="${this._config.animation_duration || 30}">
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label>Emoji Train</label>
            <input type="text" id="train_emoji" value="${this._config.train_emoji || '🚅'}">
          </div>
          <div class="field">
            <label>Emoji Gare</label>
            <input type="text" id="train_station_emoji" value="${this._config.train_station_emoji || '🚉'}">
          </div>
        </div>

        <div class="field checkbox">
          <input type="checkbox" id="train_emoji_axial_symmetry" ${this._config.train_emoji_axial_symmetry !== false ? 'checked' : ''}>
          <label>Inverser l'emoji Train (Symétrie axiale)</label>
        </div>

        <div class="field checkbox highlight">
          <input type="checkbox" id="use_real_duration" ${this._config.use_real_duration ? 'checked' : ''}>
          <label>Utiliser la durée réelle du trajet pour la vitesse</label>
        </div>

        <div class="field-row">
           <div class="field"><label>Facteur de vitesse</label>
           <input type="number" id="speed_factor" step="0.1" value="${this._config.speed_factor || 2}"></div>
        </div>

        <div class="field checkbox highlight">
          <input type="checkbox" id="show_route_details" ${this._config.show_route_details ? 'checked' : ''}>
          <label>Afficher le radar de ligne détaillé</label>
        </div>
        
        <div class="field checkbox">
          <input type="checkbox" id="show_real_stop_times" ${this._config.show_real_stop_times !== false ? 'checked' : ''}>
          <label>Afficher les retards sur chaque arrêt (Radar)</label>
        </div>
      </div>

      <style>
        .card-config { display: flex; flex-direction: column; gap: 16px; font-family: 'Roboto', sans-serif; }
        .field { display: flex; flex-direction: column; flex: 1; }
        .field-row { display: flex; gap: 16px; }
        label { margin-bottom: 4px; color: var(--secondary-text-color); font-size: 12px; font-weight: 500; }
        input[type="text"], input[type="number"] { padding: 10px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); }
        .checkbox { flex-direction: row; align-items: center; gap: 8px; }
        .checkbox input { width: 18px; height: 18px; margin: 0; }
        .highlight { background: rgba(0, 83, 156, 0.05); padding: 10px; border-radius: 6px; border-left: 4px solid #00539c; }
      </style>
    `;

    this.shadowRoot.querySelectorAll('input').forEach(input => {
      input.addEventListener('change', this.valueChanged.bind(this));
    });
  }

  valueChanged(ev) {
    if (!this._config) return;
    const target = ev.target;
    let value = target.type === 'checkbox' ? target.checked : (target.type === 'number' ? Number(target.value) : target.value);
    this._config = { ...this._config, [target.id]: value };
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this._config }, bubbles: true, composed: true }));
  }
}
customElements.define('sncf-train-card-editor', SncfTrainCardEditor);

// --- CARTE PRINCIPALE (LOGIQUE COMPLÈTE) ---
class SncfTrainCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.updateInterval = null;
    this.lastTrainSignature = null;
    this._lastRenderTime = 0;
  }

  static getConfigElement() { return document.createElement("sncf-train-card-editor"); }

  setConfig(config) {
    if (!config.device_id) throw new Error('You need to define device_id');
    this.config = {
      title: "Trains SNCF",
      train_emoji: "🚅",
      train_station_emoji: "🚉",
      train_emoji_axial_symmetry: true,
      animation_duration: 30,
      use_real_duration: true,
      speed_factor: 2,
      update_interval: 30000,
      show_real_stop_times: true,
      ...config
    };
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  connectedCallback() { this.startUpdateTimer(); }
  disconnectedCallback() { this.stopUpdateTimer(); }

  startUpdateTimer() {
    this.stopUpdateTimer();
    this.updateInterval = setInterval(async () => {
      if (this._hass) {
        this._lastRenderTime = 0;
        await this.render();
      }
    }, this.config.update_interval);
  }

  stopUpdateTimer() {
    if (this.updateInterval) { clearInterval(this.updateInterval); this.updateInterval = null; }
  }

  async getTrainEntities() {
    if (!this._hass || !this.config.device_id) return [];
    try {
      const allReg = await this._hass.callWS({ type: 'config/entity_registry/list' });
      const deviceEntities = allReg.filter(e => e.device_id === this.config.device_id);
      const trainEntities = deviceEntities.filter(e => e.entity_id.includes('train'))
        .map(e => this._hass.states[e.entity_id])
        .filter(e => e && e.attributes && e.attributes.departure_time);
      
      const now = new Date();
      return trainEntities.filter(e => this.parseTime(e.attributes.departure_time) >= now)
        .sort((a, b) => this.parseTime(a.attributes.departure_time) - this.parseTime(b.attributes.departure_time))
        .slice(0, this.config.train_lines || 3);
    } catch (e) { return []; }
  }

  parseTime(t) {
    if (!t || !t.includes(' - ')) return new Date(0);
    const p = t.split(' - '), d = p[0].split('/'), h = p[1].split(':');
    return new Date(d[2], d[1]-1, d[0], h[0], h[1]);
  }

  render() {
    if (!this._hass || !this.config) return;
    
    const nowTs = Date.now();
    if (nowTs - this._lastRenderTime < 1000) return;
    this._lastRenderTime = nowTs;

    this.getTrainEntities().then(trains => {
      const currentTime = new Date();
      const trainLinesHTML = trains.map(train => {
        const attrs = train.attributes;
        const dep = this.parseTime(attrs.departure_time);
        const diff = (dep - currentTime) / 60000;
        const maxAnim = this.config.animation_duration || 30;
        
        const pos = diff > maxAnim ? -10 : (diff <= 0 ? 100 : ((maxAnim - diff) / maxAnim) * 100);
        
        const hasDelay = attrs.has_delay || false;
        const isCanceled = attrs.canceled || false;
        
        let animDur = this.config.use_real_duration && attrs.duration_minutes ? 
                      attrs.duration_minutes * (this.config.speed_factor || 2) : 30;

        let timelineHTML = '';
        if (this.config.show_route_details && attrs.stops_schedule) {
          timelineHTML = `
            <div class="timeline-wrapper">
              <div class="timeline-line ${hasDelay?'delayed-line':''}"></div>
              <div class="timeline-container">
                ${attrs.stops_schedule.map(s => {
                  const isDeleted = s.effect === 'deleted';
                  const isAdded = s.effect === 'added';
                  const isStopDelayed = this.config.show_real_stop_times && s.amended_time && s.base_time && (s.amended_time !== s.base_time);
                  
                  const displayTime = isStopDelayed ? 
                    `<span class="base-time-radar">${s.base_time}</span><span class="amended-time-radar">${s.amended_time}</span>` : 
                    `<span>${s.base_time || s.time}</span>`;
                  
                  let statusBadge = "";
                  if (isDeleted) statusBadge = ' <span class="badge-stop deleted">SUPPRIMÉ</span>';
                  else if (isAdded) statusBadge = ' <span class="badge-stop added">RAJOUTÉ</span>';

                  return `
                    <div class="timeline-stop">
                      <div class="timeline-dot ${isDeleted?'deleted-dot':(isAdded?'added-dot':(isStopDelayed?'delayed-dot':''))}"></div>
                      <div class="timeline-time">${displayTime}</div>
                      <div class="timeline-name" style="${isDeleted?'text-decoration:line-through;opacity:0.5':''}">
                        ${s.name}${statusBadge}
                      </div>
                    </div>`;
                }).join('')}
              </div>
            </div>`;
        }

        const timeOnly = (t) => t ? t.split(' - ')[1] : "--:--";

        return `
          <div class="train-line-container" style="${isCanceled ? 'opacity: 0.7;' : ''}">
            <div class="train-line">
              <div class="train-track ${(hasDelay || isCanceled) ? 'delayed' : ''}">
                ${pos >= 0 && pos <= 100 ? `
                  <div class="train-emoji ${this.config.train_emoji_axial_symmetry?'train-emoji-axial-symmetry':''}" 
                       style="left:${pos}%; animation: moveTrain ${animDur}s linear infinite; ${isCanceled ? 'top: -30px;' : ''}">
                    ${isCanceled ? '❌' : this.config.train_emoji}
                  </div>
                ` : ''}
              </div>
              <div class="station">
                <div class="station-emoji">${this.config.train_station_emoji}</div>
                <div class="station-info">
                  <div class="arrival-time">${hasDelay ? `<span class="original-time">${timeOnly(attrs.base_departure_time)}</span><span class="real-time-delay">${timeOnly(attrs.departure_time)}</span>` : timeOnly(attrs.departure_time)}</div>
                  <div class="delay-info ${isCanceled ? 'canceled-text' : (hasDelay ? 'delay-orange' : 'on-time')}">
                    ${isCanceled ? 'ANNULÉ' : (hasDelay ? `+${attrs.delay_minutes}min` : 'À l\'heure')}
                  </div>
                  ${attrs.delay_cause ? `<div class="delay-cause">${attrs.delay_cause}</div>` : ''}
                </div>
              </div>
            </div>
            ${timelineHTML}
          </div>`;
      }).join('');

      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding: 20px; background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); overflow: hidden; }
          .train-header { font-size: 1.4em; font-weight: 700; color: var(--primary-color, #00539c); border-bottom: 2px solid var(--divider-color); padding-bottom: 12px; margin-bottom: 25px; }
          .train-line-container { margin-bottom: 30px; }
          .train-line { display: flex; align-items: center; position: relative; height: 60px; }
          .train-track { position: relative; flex: 1; height: 10px; background: #eee; border-radius: 5px; margin: 0 15px; }
          .train-track.delayed { background: #ffebee; }
          .train-track::before { content: ''; position: absolute; top: 50%; left: 0; right: 0; height: 2px; background: repeating-linear-gradient(90deg, #ccc 0, #ccc 10px, transparent 10px, transparent 20px); transform: translateY(-50%); }
          .train-emoji { position: absolute; top: -38px; font-size: 2.2em; transform: translateX(-50%); z-index: 5; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2)); display: flex; align-items: center; justify-content: center; line-height: 1; }
          .train-emoji-axial-symmetry { transform: translateX(-50%) scaleX(-1); }
          @keyframes moveTrain { 0%, 100% { margin-top: 0; } 50% { margin-top: 2px; } }
          .station { display: flex; align-items: center; gap: 10px; min-width: 140px; justify-content: flex-end; }
          .station-emoji { font-size: 1.8em; }
          .arrival-time { font-size: 1.2em; font-weight: 600; color: var(--primary-color); }
          .original-time { text-decoration: line-through; color: var(--secondary-text-color); font-size: 0.8em; margin-right: 5px; opacity: 0.6; }
          .real-time-delay { color: #ff9800; font-weight: 800; }
          .delay-orange { color: #ff9800; font-weight: 700; font-size: 0.9em; }
          .on-time { color: #4caf50; font-weight: 700; font-size: 0.9em; }
          .canceled-text { color: #f44336; font-weight: 900; }
          .delay-cause { font-size: 0.7em; font-style: italic; opacity: 0.8; color: var(--secondary-text-color); text-align: right; }
          
          /* Radar Styles */
          .timeline-wrapper { position: relative; margin-top: 15px; padding: 0 10px; }
          .timeline-line { position: absolute; top: 7px; left: 35px; right: 35px; height: 2px; background: var(--primary-color); opacity: 0.2; }
          .timeline-line.delayed-line { background: #ff9800; opacity: 0.5; }
          .timeline-container { display: flex; justify-content: space-between; position: relative; z-index: 2; }
          .timeline-stop { display: flex; flex-direction: column; align-items: center; width: 90px; }
          .timeline-dot { width: 14px; height: 14px; border-radius: 50%; background: var(--card-background-color); border: 3px solid var(--primary-color); margin-bottom: 6px; box-sizing: border-box; }
          .timeline-dot.delayed-dot { border-color: #ff9800; }
          .timeline-dot.deleted-dot { background: #f44336; border-color: #f44336; }
          .timeline-dot.added-dot { border-color: #ff9800; border-style: dashed; }
          .timeline-time { font-size: 0.75em; font-weight: bold; }
          .base-time-radar { text-decoration: line-through; opacity: 0.5; font-size: 0.9em; margin-right: 3px; }
          .amended-time-radar { color: #ff9800; font-weight: bold; }
          .timeline-name { font-size: 0.65em; text-align: center; color: var(--secondary-text-color); line-height: 1.2; }
          .badge-stop { font-size: 0.8em; font-weight: bold; padding: 1px 3px; border-radius: 3px; color: white; }
          .badge-stop.deleted { background: #f44336; }
          .badge-stop.added { background: #ff9800; }
        </style>
        <ha-card>
          <div class="train-header">${this.config.title}</div>
          ${trainLinesHTML}
        </ha-card>`;
    });
  }
}
customElements.define('sncf-train-card', SncfTrainCard);