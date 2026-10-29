/* SNCF Train Card — modernisation graphique, compatible avec SNCF-API-HA.
 * Carte autonome, sans dépendance, utilisant les capteurs et device_id existants.
 */
globalThis.customCards ||= [];
if (!globalThis.customCards.some(c => c.type === 'sncf-train-card')) {
  globalThis.customCards.push({type:'sncf-train-card',name:'SNCF Train Card',description:'Horaires SNCF avec rails modernisés',preview:true,configurable:true});
}
class SncfTrainCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this._timer=null;
    this._registry=null;
    this._registryPromise=null;
    this._renderId=0;
    this._activeDirection=0;
    this._expanded={};
    this._signature='';
    this._painted=false;
  }
  setConfig(config) {
    if (!config.device_id || (Array.isArray(config.device_id) && !config.device_id.length)) throw Error('device_id obligatoire');
    const ids=(Array.isArray(config.device_id)?config.device_id:[config.device_id]).filter(Boolean);
    this.config={
      title:'Trains SNCF',train_lines:10,visible_trains:3,direction_titles:'',animation_duration:30,update_interval:30,
      train_emoji:'mdi:train',train_emoji_axial_symmetry:false,
      show_track:true,show_duration:true,show_status:true,show_countdown:true,
      ...config,device_id:ids
    };
    // Compatibilité : anciennes configurations exprimées en millisecondes.
    // Les anciennes valeurs étaient au minimum de 5000 ms.
    if (Number(this.config.update_interval) >= 5000) {
      this.config.update_interval = Number(this.config.update_interval) / 1000;
    }
    this._registry=null;
    this._painted=false;
    this._signature='';
    this._renderId++;
    this._startTimer();
    this.render();
  }
  static getConfigForm() {
    const bool=n=>({name:n,selector:{boolean:{}}});
    return {
      schema:[
        {name:'device_id',required:true,selector:{device:{multiple:true,filter:{integration:'sncf_trains'}}}},
        {name:'title',selector:{text:{}}},
        {name:'visible_trains',selector:{number:{min:1,max:10,step:1}}},
        {name:'direction_titles',selector:{text:{}}},
        {name:'train_lines',selector:{number:{min:1,max:10,step:1}}},
        {name:'animation_duration',selector:{number:{min:0,max:100,step:1}}},
        {name:'update_interval',selector:{number:{min:5,max:3600,step:1}}},
        bool('show_countdown'),bool('show_track'),bool('show_duration'),bool('show_status'),
        {name:'train_emoji',selector:{icon:{}}},
        bool('train_emoji_axial_symmetry')
      ],
      computeLabel:s=>({
        device_id:'Appareils SNCF',title:'Titre',visible_trains:'Trains affichés avant Voir plus',direction_titles:'Titres des directions (séparés par |)',train_lines:'Nombre de trains',
        animation_duration:'Afficher le train avant départ (minutes)',
        update_interval:'Actualisation (secondes)',
        show_countdown:'Compte à rebours avant le départ',show_track:'Afficher le rail',show_duration:'Afficher la durée',
        show_status:'Afficher le statut',train_emoji:'Icône du train',
        train_emoji_axial_symmetry:'Inverser horizontalement le train'
      })[s.name]
    };
  }
  static getStubConfig(){return {device_id:[],title:'Trains SNCF',train_lines:5,show_track:true};}
  set hass(value){this._hass=value;this.render();}
  connectedCallback(){this._startTimer();}
  disconnectedCallback(){this._stopTimer();this._renderId++;}
  getCardSize(){return Math.max(2,Math.ceil(((this.config?.train_lines||3)+1)/2));}
  _stopTimer(){if(this._timer){clearInterval(this._timer);this._timer=null;}}
  _startTimer(){
    this._stopTimer();
    if(!this.isConnected||!this.config)return;
    this._timer=setInterval(()=>this.render(),Math.max(5,Number(this.config.update_interval)||30)*1000);
  }
  async _entities(){
    if(!this._registry){
      if(!this._registryPromise)this._registryPromise=this._hass.callWS({type:'config/entity_registry/list'})
        .then(data=>{this._registry=data;return data;})
        .finally(()=>{this._registryPromise=null;});
      await this._registryPromise;
    }
    const now=Date.now();
    const limit=Math.max(1,Math.min(30,Number(this.config.train_lines)||10));
    return this.config.device_id.map(deviceId=>{
      const trains=this._registry
        .filter(e=>e.device_id===deviceId&&e.entity_id.startsWith('sensor.')&&e.entity_id.includes('train'))
        .map(e=>this._hass.states[e.entity_id])
        .filter(e=>e?.attributes?.departure_time&&e.attributes.arrival_time)
        .filter(e=>{const t=this._date(e.attributes.arrival_time);return Number.isFinite(t)&&t+30*60000>=now;})
        .sort((a,b)=>this._date(a.attributes.departure_time)-this._date(b.attributes.departure_time))
        .slice(0,limit);
      return {deviceId,trains};
    });
  }
  _date(value){
    if(!value)return NaN;
    const m=String(value).match(/^(\d{2})\/(\d{2})\/(\d{4})\s*-\s*(\d{2}):(\d{2})$/);
    if(m)return new Date(+m[3],+m[2]-1,+m[1],+m[4],+m[5]).getTime();
    return new Date(value).getTime();
  }
  _time(v){const d=this._date(v);return Number.isFinite(d)?new Date(d).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'--:--';}
  _escape(v){return String(v===undefined||v===null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  _icon(value,fallback){
    const v=String(value||fallback||'');
    return /^[a-z][a-z0-9-]*:[a-z0-9-]+$/i.test(v)
      ?`<ha-icon icon="${this._escape(v)}"></ha-icon>`
      :`<span class="emoji">${this._escape(v)}</span>`;
  }
  _line(entity){
    const a=entity.attributes,now=Date.now(),dep=this._date(a.departure_time),arr=this._date(a.arrival_time);
    const baseDep=this._time(a.base_departure_time||a.departure_time);
    const baseArr=this._time(a.base_arrival_time||a.arrival_time);
    const realDep=this._time(a.departure_time),realArr=this._time(a.arrival_time);
    const delay=Math.max(0,Number(a.delay_minutes)||0),late=delay>0||!!a.has_delay;
    const running=now>=dep&&now<arr,arrived=now>=arr;
    const state=late?(delay>15?'late severe':'late moderate'):running?'running':arrived?'arrived':'ontime';
    const label=late?`+${delay} min`:running?'En circulation':arrived?'Arrivé':'À l’heure';
    const duration=Number(a.duration_minutes);
    const progress=arr>dep?Math.max(0,Math.min(100,(now-dep)/(arr-dep)*100)):0;
    const showTrain=running;
    const time=(base,real)=>late&&base!==real
      ?`<span class="original">${this._escape(base)}</span><span class="actual">${this._escape(real)}</span>`
      :`<span class="actual">${this._escape(real)}</span>`;
    const durationLabel=Number.isFinite(duration)&&duration>0?`${Math.round(duration)} min`:'';
    const countdown=this.config.show_countdown&&now<dep?`<span class="countdown" data-departure="${dep}">${this._countdown(dep,now)}</span>`:'';
    return `<article class="train-row ${state}">
      <div class="journey">
        <div class="station depart"><span class="station-caption">Départ</span>
          <div class="times">${time(baseDep,realDep)}</div></div>
        <div class="middle">
          ${this.config.show_track?`<div class="track">
            <div class="track-fill" style="width:${running||arrived?progress:0}%"></div>
            ${showTrain?`<span class="moving-train" style="left:${progress}%">${this._icon(this.config.train_emoji,'mdi:train')}</span>`:''}
          </div>`:'<ha-icon icon="mdi:arrow-right"></ha-icon>'}
        </div>
        <div class="station arrive"><span class="station-caption">Arrivée</span>
          <div class="times">${time(baseArr,realArr)}</div></div>
      </div>
      <div class="train-footer">
        <div class="train-meta"><span class="ter-pill">TER</span>
          ${this.config.show_duration&&durationLabel?`<span class="duration"><ha-icon icon="mdi:clock-outline"></ha-icon>${durationLabel}</span>`:''}
          ${countdown}
        </div>
        ${this.config.show_status?`<span class="status"><span class="dot"></span>${label}</span>`:''}
      </div>
    </article>`;
  }
  _countdown(dep,now=Date.now()){
    const diff=dep-now;
    if(!Number.isFinite(diff)||diff<=0)return '';
    const minutes=Math.ceil(diff/60000);
    if(minutes>=1440)return `Dans ${Math.floor(minutes/1440)} j`;
    if(minutes>=60)return `Dans ${Math.floor(minutes/60)} h ${String(minutes%60).padStart(2,'0')}`;
    return `Dans ${minutes} min`;
  }
  _updateLive(groups){
    const now=Date.now();
    this.shadowRoot.querySelectorAll('[data-departure]').forEach(el=>{
      const dep=Number(el.dataset.departure);
      el.textContent=this._countdown(dep,now);
      el.hidden=now>=dep;
    });

  }
  _directionName(group,index){
    const configured=String(this.config.direction_titles||'').split('|').map(s=>s.trim());
    if(configured[index])return configured[index];
    const a=group.trains[0]?.attributes;
    return a?.route_name||a?.direction||`Trajet ${index+1}`;
  }
  _view(groups){
    if(!groups.length)return '<p class="empty">Aucun trajet configuré.</p>';
    const index=Math.max(0,Math.min(this._activeDirection,groups.length-1));
    const group=groups[index],count=group.trains.length;
    const visible=Math.max(1,Number(this.config.visible_trains)||3);
    const expanded=!!this._expanded[group.deviceId];
    const shown=expanded?group.trains:group.trains.slice(0,visible);
    const name=this._escape(this._directionName(group,index));
    return `<nav aria-label="Choix du sens">
       <button type="button" class="arrow-btn" data-prev aria-label="Sens précédent"><ha-icon icon="mdi:chevron-left"></ha-icon></button>
       <div class="direction-label"><span>${name}</span><small>${index+1} / ${groups.length} · ${count} trains</small></div>
       <button type="button" class="arrow-btn" data-next aria-label="Sens suivant"><ha-icon icon="mdi:chevron-right"></ha-icon></button>
     </nav>
     <div class="direction-dots" aria-hidden="true">${groups.map((g,i)=>`<span class="${i===index?'active':''}"></span>`).join('')}</div>
     <div class="trains">${shown.length?shown.map(t=>this._line(t)).join(''):'<p class="empty">Aucun train disponible pour ce sens.</p>'}</div>
     ${count>visible?`<button type="button" class="more" data-more aria-expanded="${expanded}">${expanded?'Voir moins':`Voir plus (${count-visible} trains)`} <ha-icon icon="mdi:chevron-${expanded?'up':'down'}"></ha-icon></button>`:''}
     <p class="cancellation-note"><ha-icon icon="mdi:information-outline"></ha-icon><span>Les trains supprimés ne sont pas pris en compte.</span></p>`;
  }
  _attachActions(groups){
    const panel=this.shadowRoot.querySelector('.panel');
    panel.querySelector('[data-prev]')?.addEventListener('click',()=>{
      this._activeDirection=(this._activeDirection+groups.length-1)%groups.length;this._updatePanel(groups);
    });
    panel.querySelector('[data-next]')?.addEventListener('click',()=>{
      this._activeDirection=(this._activeDirection+1)%groups.length;this._updatePanel(groups);
    });
    panel.querySelector('[data-more]')?.addEventListener('click',()=>{
      const id=groups[this._activeDirection].deviceId;
      this._expanded[id]=!this._expanded[id];
      this._updatePanel(groups);
    });
  }
  _updatePanel(groups){
    const panel=this.shadowRoot.querySelector('.panel');
    if(!panel)return;
    panel.innerHTML=this._view(groups);
    this._attachActions(groups);
    this._updateLive(groups);
  }
  async render(){
    if(!this.config||!this._hass||!this.isConnected)return;
    const id=++this._renderId;
    try{
      const groups=await this._entities();
      if(id!==this._renderId||!this.isConnected)return;
      const signature=JSON.stringify(groups.map(g=>[g.deviceId,g.trains.map(t=>[
        t.entity_id,t.attributes.departure_time,t.attributes.arrival_time,
        t.attributes.base_departure_time,t.attributes.base_arrival_time,
        t.attributes.delay_minutes,t.attributes.has_delay
      ])]));
      // Avoid replacing the DOM on every Home Assistant state update.
      // This prevents focus/scroll jumps on iOS.
      if(this._painted&&signature===this._signature){this._updateLive(groups);return;}
      this._signature=signature;
      if(!this._painted){
        this.shadowRoot.innerHTML=`<style>${this._css()}</style><ha-card>
          <header><ha-icon icon="mdi:train"></ha-icon><span>${this._escape(this.config.title)}</span></header>
          <div class="panel"></div></ha-card>`;
        this._painted=true;
      }
      this._updatePanel(groups);
    }catch(e){
      if(id!==this._renderId)return;
      if(!this._painted){
        this.shadowRoot.innerHTML=`<ha-card><div style="padding:16px">Impossible de charger les trains : ${this._escape(e.message)}</div></ha-card>`;
      }
    }
  }
  _css(){return `
:host{display:block;min-width:0;max-width:100%;overflow-anchor:none;--accent:var(--primary-color,#4c91ff)}
*{box-sizing:border-box}
ha-card{width:100%;max-width:100%;min-width:0;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color);border-radius:20px;overflow:hidden;border:1px solid var(--divider-color);box-shadow:0 8px 24px rgba(0,0,0,.08)}
header{display:flex;align-items:center;gap:10px;padding:17px 16px 12px;font-weight:750;font-size:1.1rem}
header ha-icon{color:var(--accent)}
.panel,.trains{overflow-anchor:none;min-width:0;max-width:100%}
nav{display:flex;align-items:center;gap:7px;margin:2px 12px 0;padding:8px 5px;border-radius:15px;background:var(--secondary-background-color,rgba(100,120,160,.09));border:1px solid var(--divider-color)}
.arrow-btn{display:grid;place-items:center;flex:0 0 36px;width:36px;height:38px;border:0;border-radius:11px;background:var(--card-background-color,rgba(100,120,160,.15));color:var(--accent);cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.direction-label{flex:1;min-width:0;text-align:center;line-height:1.3}
.direction-label span{display:block;font-size:.92rem;font-weight:750;overflow-wrap:anywhere}
.direction-label small{display:block;color:var(--secondary-text-color);font-size:.7rem;margin-top:4px}
.direction-dots{display:flex;justify-content:center;gap:6px;padding:10px 0 5px}
.direction-dots span{width:5px;height:5px;border-radius:9px;background:var(--divider-color)}
.direction-dots span.active{width:19px;background:var(--accent)}
.trains{padding:2px 12px 0}
.train-row{min-width:0;max-width:100%;overflow:hidden;padding:13px 12px 11px;margin:9px 0;border-radius:15px;border:1px solid var(--divider-color);background:var(--secondary-background-color,rgba(100,120,160,.07))}
.journey{display:grid;grid-template-columns:minmax(0,auto) minmax(16px,1fr) minmax(0,auto);align-items:center;gap:8px;min-width:0;width:100%}
.station{display:flex;flex-direction:column;gap:3px;min-width:0;max-width:100%}
.station.arrive{text-align:right}
.station-caption{font-size:.59rem;text-transform:uppercase;letter-spacing:.08em;color:var(--secondary-text-color);font-weight:650}
.times{display:flex;flex-direction:column;gap:2px;line-height:1.15;font-variant-numeric:tabular-nums}
 .actual{font-size:clamp(.94rem,4.5vw,1.27rem);font-weight:800;letter-spacing:-.035em;white-space:nowrap}
.original{font-size:.72rem;color:var(--secondary-text-color);text-decoration:line-through}
.middle{min-width:16px;display:flex;align-items:center;justify-content:center;position:relative}
.track{height:4px;width:100%;position:relative;border-radius:9px;background:var(--divider-color)}
.track::before,.track::after{content:'';position:absolute;top:-3px;width:10px;height:10px;border-radius:50%;background:var(--secondary-text-color);opacity:.55}
.track::before{left:0}.track::after{right:0}
.track-fill{height:100%;background:var(--accent);border-radius:9px;transition:width .5s ease}
.moving-train{position:absolute;top:-26px;transform:translateX(-50%);color:var(--accent);transition:left .5s ease}
.moving-train ha-icon{--mdc-icon-size:23px}
.train-footer{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:7px;margin-top:12px;min-width:0}
.train-meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px;min-width:0;color:var(--secondary-text-color);font-size:.72rem}
.ter-pill{padding:3px 7px;border:1px solid var(--divider-color);border-radius:7px;font-size:.66rem;font-weight:750}
.duration{display:inline-flex;align-items:center;gap:3px;white-space:nowrap}
.duration ha-icon{--mdc-icon-size:14px}
.countdown{color:var(--accent);font-weight:700;white-space:nowrap}
.countdown[hidden]{display:none}
.status{display:inline-flex;align-items:center;gap:6px;padding:6px 9px;border-radius:9px;background:color-mix(in srgb,var(--success-color,#43a047) 12%,transparent);color:var(--success-color,#43a047);font-size:.72rem;font-weight:750;white-space:nowrap}
.dot{height:7px;width:7px;border-radius:50%;background:currentColor}
.late.moderate .actual,.late.moderate .status{color:var(--warning-color,#f59e0b)}
.late.severe .actual,.late.severe .status{color:var(--error-color,#e53935)}
.late.moderate .status{background:color-mix(in srgb,var(--warning-color,#f59e0b) 12%,transparent)}
.late.severe .status{background:color-mix(in srgb,var(--error-color,#e53935) 12%,transparent)}
.late.moderate .track-fill{background:var(--warning-color,#f59e0b)}
.late.severe .track-fill{background:var(--error-color,#e53935)}
.late.moderate .moving-train{color:var(--warning-color,#f59e0b)}
.late.severe .moving-train{color:var(--error-color,#e53935)}
.running .status{color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent)}
.arrived .status{color:var(--secondary-text-color);background:var(--secondary-background-color)}
.cancellation-note{display:flex;align-items:flex-start;justify-content:center;gap:6px;margin:8px 14px 15px;color:var(--secondary-text-color);font-size:.69rem;line-height:1.4;text-align:center}.cancellation-note ha-icon{--mdc-icon-size:15px;flex-shrink:0}
.more{display:flex;justify-content:center;align-items:center;gap:8px;width:calc(100% - 24px);margin:12px;padding:13px;border:1px solid var(--divider-color);border-radius:12px;background:var(--secondary-background-color,rgba(100,120,160,.09));color:var(--accent);font-size:.85rem;font-weight:750;cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.more ha-icon{--mdc-icon-size:19px}
.empty{padding:20px;text-align:center;color:var(--secondary-text-color)}
.cancellation-note{display:flex;justify-content:center;align-items:center;gap:6px;margin:10px 15px 15px;color:var(--secondary-text-color);font-size:.7rem;text-align:center;line-height:1.35}
.cancellation-note ha-icon{--mdc-icon-size:15px;flex-shrink:0}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(max-width:370px){.trains{padding:2px 8px 0}.train-row{padding:11px 9px}.actual{font-size:1.1rem}.journey{gap:6px}}
@media(prefers-reduced-motion:reduce){.moving-train,.track-fill{transition:none}}
  `;}
}
if(!customElements.get('sncf-train-card'))customElements.define('sncf-train-card',SncfTrainCard);
