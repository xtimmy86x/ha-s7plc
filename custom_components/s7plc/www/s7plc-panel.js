const TYPES = ["sensors", "binary_sensors", "switches", "covers", "lights", "buttons", "numbers", "texts", "climates", "entity_sync"];
// Translation JSON served by the integration is the canonical source. This
// deliberately small dictionary is only for a total translation-loading failure.
const SUPPORTED_LANGUAGES = new Set(["en", "it", "de", "pl", "cs"]);
const ENGLISH_EMERGENCY_FALLBACK = {
  loading:"Loading configuration…", no_plc:"No PLC configured",
  no_plc_help:"First add the Siemens S7 integration from Devices & services.",
  title:"S7 PLC configuration", entities:"entities", connected:"Connected",
  disconnected:"Disconnected", unknown:"Unknown", connection_details_title:"Connection details", add:"Add", empty:"No entities", entity:"Entity",
  edit:"Edit", delete:"Delete", cancel:"Cancel", save:"Save changes",
  required:"Required", required_error:"Fill in all required fields.",
  configuration_load_error:"Unable to load the YAML configuration.",
  configuration_download_error:"Unable to download the backup.",
  batch:{select_entity:"Select entity",delete_selected:"Delete selected",delete_selected_confirm:"Delete {count} selected entities?"}
};
// The control mode is deliberately virtual: the backend continues to store the
// two established booleans, so existing YAML and config entries need no migration.
const CONTROL_MODE_FROM_ENTITY = entity => entity.pulse_command ? "pulse" : entity.sync_state ? "sync" : "direct";
const APPLY_CONTROL_MODE = (entity,mode) => ({...entity,sync_state:mode==="sync",pulse_command:mode==="pulse"});
// Light mode is UI-only and inferred solely from the state address required by the backend.
const LIGHT_MODE_FROM_ENTITY = entity => entity.brightness_state_address ? "dimmable" : "on_off";
const CONNECTION_WINDOW_MS = 24*60*60*1000;
const CONNECTION_DETAIL_GROUPS = [
  {key:"connection",icon:"mdi:lan-connect",fields:["connection_type","pys7_connection_type"]},
  {key:"performance",icon:"mdi:speedometer",fields:["scan_interval","operation_timeout","optimize_read","enable_write_batching","enable_metrics"]},
  {key:"retry",icon:"mdi:reload",fields:["max_retries","retry_backoff_initial","retry_backoff_max"]}
];
const CONNECTION_DETAIL_HEADER_FIELDS = new Set(["name","host","port"]);
const CONNECTION_DETAIL_MODE_FIELDS = new Set(["rack","slot","local_tsap","remote_tsap"]);
const connectionDetailGroups = data => {
  const values=data&&typeof data==="object"?data:{},mode=values.connection_type==="tsap"?"tsap":"rack_slot";
  const definitions=CONNECTION_DETAIL_GROUPS.map(group=>group.key==="connection"?{...group,fields:[...group.fields,...(mode==="tsap"?["local_tsap","remote_tsap"]:["rack","slot"])]}:group);
  const used=new Set([...CONNECTION_DETAIL_HEADER_FIELDS,...CONNECTION_DETAIL_MODE_FIELDS]);
  const groups=definitions.map(group=>({...group,fields:group.fields.filter(key=>Object.prototype.hasOwnProperty.call(values,key)).map(key=>{used.add(key);return {key,value:values[key]};})})).filter(group=>group.fields.length);
  const other=Object.keys(values).filter(key=>!used.has(key)).map(key=>({key,value:values[key]}));
  if(other.length)groups.push({key:"other",icon:"mdi:dots-horizontal",fields:other});
  return groups;
};
const CONNECTION_STATE = state => state==="on"?"connected":state==="off"?"disconnected":"unknown";
const LIVE_CONNECTION_STATUS = (connectionState,fallback) => connectionState ? CONNECTION_STATE(connectionState.state) : fallback===true ? "connected" : fallback===false ? "disconnected" : "unknown";
const APPLY_LIVE_CONNECTION_DURATION = (result,connectionState,now=Date.now()) => {
  if(!connectionState)return {...result,currentDowntime:null,currentDurationState:"unknown"};
  const liveState=CONNECTION_STATE(connectionState?.state),changed=Date.parse(connectionState?.last_changed),hasChanged=Number.isFinite(changed)&&changed<=now;
  return {...result,currentUptime:liveState==="connected"?(hasChanged?now-changed:result.currentUptime):null,currentDowntime:liveState==="disconnected"&&hasChanged?now-changed:null,currentDurationState:liveState};
};
const BUILD_CONNECTION_AVAILABILITY = (history,now=Date.now(),windowMs=CONNECTION_WINDOW_MS) => {
  const start=now-windowMs,events=(history||[]).map(item=>({state:CONNECTION_STATE(item.state),time:Date.parse(item.last_changed||item.last_updated)})).filter(item=>Number.isFinite(item.time)&&item.time<=now).sort((a,b)=>a.time-b.time);
  const compact=[];for(const event of events){const previous=compact[compact.length-1];if(previous?.time===event.time)compact[compact.length-1]=event;else if(!previous||previous.state!==event.state)compact.push(event);}
  let state="unknown",stateSince=start,index=0;
  while(index<compact.length&&compact[index].time<=start){state=compact[index].state;stateSince=compact[index].time;index++;}
  const intervals=[];let cursor=start,disconnects=0,lastDisconnection=null;
  for(;index<compact.length;index++){const event=compact[index],at=Math.max(start,event.time);if(at>cursor)intervals.push({state,start:cursor,end:at});if(state==="connected"&&event.state==="disconnected"){disconnects++;lastDisconnection={start:event.time,end:null};}if(state==="disconnected"&&event.state!=="disconnected"&&lastDisconnection&&!lastDisconnection.end)lastDisconnection.end=event.time;state=event.state;stateSince=event.time;cursor=at;}
  if(cursor<now)intervals.push({state,start:cursor,end:now});
  if(state==="disconnected"&&lastDisconnection&&!lastDisconnection.end)lastDisconnection.end=now;
  const durations={connected:0,disconnected:0,unknown:0};for(const interval of intervals)durations[interval.state]+=interval.end-interval.start;
  const determined=durations.connected+durations.disconnected;
  return {start,now,intervals,durations,availability:determined?durations.connected/determined*100:null,disconnects,currentUptime:state==="connected"?now-stateSince:null,lastDisconnection};
};
const COMMON = [
  ["name","Nome"], ["area","Area"], ["scan_interval","Intervallo di scansione (s)","number"]
];
const FIELDS = {
  sensors:[["address","Indirizzo PLC","text",true],["device_class","Classe dispositivo"],["unit_of_measurement","Unità di misura"],["value_multiplier","Moltiplicatore","number"],["min_value","Valore minimo","number"],["max_value","Valore massimo","number"],["scale_raw_min","Scala grezza minima","number"],["scale_raw_max","Scala grezza massima","number"],["state_class","Classe di stato"],["real_precision","Decimali","number"],...COMMON],
  binary_sensors:[["address","Indirizzo PLC","text",true],["device_class","Classe dispositivo"],["invert_state","Inverti stato","checkbox"],...COMMON],
  switches:[["control_behavior","Comportamento controllo","control"],["state_address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["pulse_duration","Durata impulso (s)","number"],...COMMON],
  covers:[["cover_mode","Tipo tapparella","select",true,{traditional:"Tradizionale",position:"Posizione"}],["open_command_address","Indirizzo apertura"],["close_command_address","Indirizzo chiusura"],["cover_status_address","Cover status address"],["cover_status_open_values","Open status value(s)"],["cover_status_closed_values","Closed status value(s)"],["cover_status_opening_values","Opening status value(s)"],["cover_status_closing_values","Closing status value(s)"],["cover_status_stopped_values","Stopped status value(s)"],["opening_state_address","Stato apertura"],["closing_state_address","Stato chiusura"],["cover_opening_address","Opening status address"],["cover_closing_address","Closing status address"],["cover_stopped_address","Stopped status address"],["position_state_address","Indirizzo posizione"],["position_command_address","Comando posizione"],["stop_command_address","Comando stop"],["stop_pulse_duration","Durata impulso stop (s)","number"],["tilt_state_address","Tilt state address"],["tilt_command_address","Tilt command address"],["invert_tilt","Invert tilt","checkbox"],["operate_time","Tempo corsa (s)","number"],["use_state_topics","Usa indirizzi di stato","checkbox"],["invert_position","Inverti posizione","checkbox"],["device_class","Classe dispositivo"],...COMMON],
  lights:[["control_behavior","Comportamento controllo","control"],["light_mode","Tipo di luce","light"],["state_address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["brightness_state_address","Stato luminosità"],["brightness_command_address","Comando luminosità"],["pulse_duration","Durata impulso (s)","number"],["brightness_scale","Scala luminosità","number"],...COMMON],
  buttons:[["address","Indirizzo PLC","text",true],["button_pulse","Durata impulso (s)","number"],...COMMON.filter(x=>x[0]!=="scan_interval")],
  numbers:[["address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["device_class","Classe dispositivo"],["unit_of_measurement","Unità di misura"],["min_value","Valore minimo","number"],["max_value","Valore massimo","number"],["step","Incremento","number"],["value_multiplier","Moltiplicatore","number"],["scale_raw_min","Scala grezza minima","number"],["scale_raw_max","Scala grezza massima","number"],["real_precision","Decimali","number"],...COMMON],
  texts:[["address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["pattern","Espressione regolare"],...COMMON],
  climates:[["control_mode","Modalità controllo","select",true,{direct:"Uscite dirette",setpoint:"Setpoint"}],["current_temperature_address","Temperatura attuale","text",true],["target_temperature_address","Temperatura obiettivo"],["heating_output_address","Uscita riscaldamento"],["cooling_output_address","Uscita raffrescamento"],["heating_action_address","Stato riscaldamento"],["cooling_action_address","Stato raffrescamento"],["preset_mode_address","Modalità preset"],["preset_mode_bidirectional","Preset mode bidirectional","checkbox"],["on_off_address","On/off address"],["preset_mode_off_value","Off mode value","number"],["preset_mode_heat_value","Heat mode value","number"],["preset_mode_cool_value","Cool mode value","number"],["preset_mode_heat_cool_value","Heat/Cool mode value","number"],["preset_mode_auto_value","Auto mode value","number"],["preset_mode_dry_value","Dry mode value","number"],["preset_mode_fan_only_value","Fan only mode value","number"],["hvac_status_address","Stato HVAC"],["hvac_status_off_values","Off status value(s)"],["hvac_status_heating_values","Heating status value(s)"],["hvac_status_cooling_values","Cooling status value(s)"],["hvac_status_idle_values","Idle status value(s)"],["hvac_status_drying_values","Drying status value(s)"],["hvac_status_fan_values","Fan status value(s)"],["hvac_status_preheating_values","Preheating status value(s)"],["hvac_status_defrosting_values","Defrosting status value(s)"],["min_temp","Temperatura minima","number"],["max_temp","Temperatura massima","number"],["temp_step","Incremento temperatura","number"],...COMMON],
  entity_sync:[["source_entity","Entità Home Assistant","text",true],["address","Indirizzo PLC","text",true],["invert_state","Inverti stato","checkbox"],...COMMON.filter(x=>x[0]!=="scan_interval")]
};
// Campi da nascondere/rimuovere in base alla modalità selezionata (usato sia dall'editor che dal salvataggio)
const MODE_HIDDEN = {
  covers: {
    position:    ["open_command_address","close_command_address","opening_state_address","closing_state_address","cover_opening_address","cover_closing_address","cover_stopped_address","operate_time","use_state_topics"],
    traditional: ["position_state_address","position_command_address","stop_command_address","stop_pulse_duration","tilt_state_address","tilt_command_address","invert_tilt","invert_position"]
  },
  climates: {
    setpoint: ["heating_output_address","cooling_output_address","heating_action_address","cooling_action_address"],
    direct:   ["target_temperature_address","preset_mode_address","preset_mode_bidirectional","on_off_address","preset_mode_off_value","preset_mode_heat_value","preset_mode_cool_value","preset_mode_heat_cool_value","preset_mode_auto_value","preset_mode_dry_value","preset_mode_fan_only_value","hvac_status_address","hvac_status_off_values","hvac_status_heating_values","hvac_status_cooling_values","hvac_status_idle_values","hvac_status_drying_values","hvac_status_fan_values","hvac_status_preheating_values","hvac_status_defrosting_values"]
  }
};
// Climate (setpoint mode): these values also determine which HVAC modes are
// exposed, even when no preset_mode_address is configured.
const CLIMATE_PRESET_VALUE_FIELDS = ["preset_mode_off_value","preset_mode_heat_value","preset_mode_cool_value","preset_mode_heat_cool_value","preset_mode_auto_value","preset_mode_dry_value","preset_mode_fan_only_value"];
// Historical implicit defaults for the 4 "core" preset mode values, kept
// only for legacy/never-configured climates: a key genuinely absent from
// the item (not present at all, as opposed to explicitly null/disabled)
// pre-fills with these instead of showing blank, so opening and saving a
// pre-existing or brand-new climate in the panel without touching these
// fields doesn't silently disable OFF/HEAT/COOL/HEAT_COOL.
const CLIMATE_PRESET_CORE_DEFAULTS = {preset_mode_off_value:0,preset_mode_heat_value:1,preset_mode_cool_value:2,preset_mode_heat_cool_value:3};
// Same idea, mirrored on the status-matching side: hvac_status_off/
// heating/cooling_values also carry non-empty historical defaults ("0"/
// "1"/"2"), unlike idle/drying/fan/preheating/defrosting which default to
// "". Without this, a never-configured (or legacy) climate shows these 3
// fields as blank while climate.py still matches status 0/1/2 against
// them internally - confusingly making e.g. a status address report
// "Cooling" while the panel shows the cooling field empty.
const CLIMATE_STATUS_CORE_DEFAULTS = {hvac_status_off_values:"0",hvac_status_heating_values:"1",hvac_status_cooling_values:"2"};
// Climate (setpoint mode): the per-status match values are meaningless
// without hvac_status_address filled in — nothing to match them against.
const CLIMATE_STATUS_VALUE_FIELDS = ["hvac_status_off_values","hvac_status_heating_values","hvac_status_cooling_values","hvac_status_idle_values","hvac_status_drying_values","hvac_status_fan_values","hvac_status_preheating_values","hvac_status_defrosting_values"];
// Address fields that are a single PLC bit (BOOL), not a REAL/word value —
// shown with a BOOL-flavored placeholder/example instead of the default
// REAL one.
const BOOL_FIELDS = {
  binary_sensors: [
    "address"
  ],
  switches: [
    "state_address",
    "command_address"
  ],
  lights: [
    "state_address",
    "command_address"
  ],
  buttons: [
    "address"
  ],
  covers: [
    "open_command_address",
    "close_command_address",
    "opening_state_address",
    "closing_state_address",
    "cover_opening_address",
    "cover_closing_address",
    "cover_stopped_address",
    "stop_command_address"
  ],
  climates: [
    "heating_output_address",
    "cooling_output_address",
    "heating_action_address",
    "cooling_action_address",
    "on_off_address"
  ]
};
// Text entity addresses point to STRING/WSTRING values rather than the
// default REAL value used by other address fields.
const STRING_FIELDS = {
  texts: ["address","command_address"]
};
// Meaningless (and hidden in the editor) without cover_status_address
// filled in first, in either cover mode — there's nothing for them to
// match against.
const COVER_STATUS_VALUE_FIELDS = ["cover_status_open_values","cover_status_closed_values","cover_status_opening_values","cover_status_closing_values","cover_status_stopped_values"];
// Position cover: invert_tilt has nothing to invert without tilt_state_address
// configured, so it's hidden (and stripped on save) until then.
const COVER_TILT_INVERT_FIELDS = ["invert_tilt"];

class S7PlcConfigurationPanel extends HTMLElement {
  connectedCallback(){this.selectedIndices??=new Set();this._statusTimer??=setInterval(()=>this.refreshConnectionStatus(),5000);}
  disconnectedCallback(){clearInterval(this._statusTimer);this._statusTimer=null;}
  set hass(value) { const previous=this.language; this._hass = value; if (!this._loaded) this.load(); else if(previous!==this.language)this.loadFlowTranslations().then(()=>this.render()); else this.updateStates(); this.syncMenuButtons(); }
  set panel(value) { this._panel = value; if(this._loaded&&this.entries)this.render(); }
  set narrow(value) { this._narrow = value; this.syncMenuButtons(); }
  // Custom panels must render their own ha-menu-button: without it the HA
  // sidebar cannot be opened on narrow (mobile) screens.
  menuButton(){return '<ha-menu-button></ha-menu-button>';}
  banner(){
    const version=this.integrationVersion?`?v=${encodeURIComponent(this.integrationVersion)}`:'';
    return `<div class="hero-banner"><img src="/s7plc_static/s7plc-header.png${version}" alt="ha-s7plc"></div>`;
  }
  panelActions(className){
    return `<div class="${className}"><button class="config-yaml" data-config-yaml title="${this.t('configuration_yaml')}" aria-label="${this.t('configuration_yaml')}"><ha-icon icon="mdi:file-code-outline"></ha-icon><span>${this.t('configuration_yaml')}</span></button><select data-entry-selector aria-label="PLC">${this.entries.map(e=>`<option value="${this.escape(e.entry_id)}" ${e.entry_id===this.entryId?'selected':''}>${this.escape(e.title)}</option>`).join('')}</select>${this.integrationVersion?`<span class="integration-version">v${this.escape(this.integrationVersion)}</span>`:''}</div>`;
  }
  syncMenuButtons(){this.querySelectorAll('ha-menu-button').forEach(b=>{b.hass=this._hass;b.narrow=this._narrow;});}
  get integrationVersion(){return this._panel?.config?.version||'';}
  get language(){const language=(this._hass?.locale?.language||this._hass?.language||"en").toLowerCase().split(/[-_]/)[0];return SUPPORTED_LANGUAGES.has(language)?language:"en";}
  translation(path,source){return path.split('.').reduce((value,key)=>value?.[key],source);}
  t(path){return this.translation(`config_panel.${path}`,this.flowTranslations)??this.translation(path,ENGLISH_EMERGENCY_FALLBACK)??path;}
  bt(key,values={}){const text=this.t(`batch.${key}`);return Object.entries(values).reduce((result,[name,value])=>result.replace(`{${name}}`,value),text);}
  async loadFlowTranslations(){
    const requested=this.language, languages=requested==="en"?["en"]:[requested,"en"];
    this.flowTranslations=null;
    for(const language of languages){
      try{const response=await fetch(`/s7plc_translations/${language}.json`);if(!response.ok)throw Error(`HTTP ${response.status}`);this.flowTranslations=await response.json();return;}
      catch(err){console.warn(`Unable to load S7 PLC translations for ${language}`,err);}
    }
  }
  async load() {
    if (!this._hass) return; this._loaded = true;
    this.innerHTML = `<style>${this.styles}</style><div class="menubar">${this.menuButton()}</div><div class="loading">${this.t('loading')}</div>`;
    this.syncMenuButtons();
    try { [this.entries] = await Promise.all([this._hass.callWS({type:"s7plc/config/list"}),this.loadFlowTranslations()]); this.entryId ||= this.entries[0]?.entry_id; this.render(); }
    catch (err) { this.innerHTML = `<style>${this.styles}</style><div class="menubar">${this.menuButton()}</div><ha-alert alert-type="error">${this.escape(err.message || err)}</ha-alert>`; this.syncMenuButtons(); }
  }
  async refreshConnectionStatus(){
    if(!this._hass||!this._loaded||this._refreshingStatus)return;
    this._refreshingStatus=true;
    try{this.entries=await this._hass.callWS({type:"s7plc/config/list"});const entry=this.entries.find(e=>e.entry_id===this.entryId),badge=this.querySelector('.connection-badge');if(entry&&badge){const status=this.connectionStatus(entry);badge.classList.toggle('connected',status==="connected");badge.classList.toggle('unknown',status==="unknown");badge.setAttribute('aria-label',this.connectionBadgeAriaLabel(status));badge.innerHTML=this.connectionBadgeContent(status);}}
    catch(err){console.debug("Unable to refresh S7 PLC connection status",err);}
    finally{this._refreshingStatus=false;}
  }
  render() {
    const entry=this.entries.find(e=>e.entry_id===this.entryId);
    if(!entry){
      this.innerHTML=`<style>${this.styles}</style><div class="page"><div class="mobile-controls">${this.menuButton()}</div>${this.banner()}<div class="empty"><ha-icon icon="mdi:chip"></ha-icon><h2>${this.t('no_plc')}</h2><p>${this.t('no_plc_help')}</p></div></div>`;
      this.syncMenuButtons();
      return;
    }
    const count=TYPES.reduce((n,t)=>n+entry.entities[t].length,0), type=this.type||TYPES[0],status=this.connectionStatus(entry);
    this.innerHTML=`<style>${this.styles}</style><div class="page"><div class="mobile-controls">${this.menuButton()}${this.panelActions('mobile-actions')}</div>${this.banner()}<div class="summary"><div class="summary-info"><ha-icon icon="mdi:memory"></ha-icon><div class="plc-details"><span class="plc-title"><b>${this.escape(entry.title)}</b><button type="button" class="connection-badge ${status==='connected'?'connected':status==='unknown'?'unknown':''}" title="${this.t('connection_details_help')}" aria-label="${this.connectionBadgeAriaLabel(status)}">${this.connectionBadgeContent(status)}</button></span><span>${this.escape(entry.data.host||'')} · ${count} ${this.t('entities')}</span></div></div>${this.panelActions('summary-actions')}</div><nav>${TYPES.map(t=>`<button data-type="${t}" class="${t===type?'active':''}"><ha-icon icon="mdi:${this.icon(t)}"></ha-icon>${this.t(`types.${t}`)} <span>${entry.entities[t].length}</span></button>`).join('')}</nav><main><div class="toolbar"><div><h2>${this.t(`types.${type}`)}</h2><p>${this.t('reload_help')}</p></div><div class="toolbar-actions"><button class="batch-delete danger" id="delete-selected" hidden><ha-icon icon="mdi:delete-sweep"></ha-icon><span></span></button><button class="primary" id="add"><ha-icon icon="mdi:plus"></ha-icon> ${this.t('add')}</button></div></div><div class="cards">${this.entityCards(entry)}</div></main></div>`;
    this.querySelectorAll('[data-entry-selector]').forEach(selector=>selector.onchange=e=>{this.entryId=e.target.value;this.selectedIndices.clear();this.render();});
    this.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{this.type=b.dataset.type;this.selectedIndices.clear();this.render();});
    this.querySelector('#add').onclick=()=>this.openEditor();
    this.querySelector('#delete-selected').onclick=()=>this.remove([...this.selectedIndices]);
    this.querySelectorAll('[data-select]').forEach(input=>input.onchange=()=>{const index=Number(input.dataset.select);if(input.checked)this.selectedIndices.add(index);else this.selectedIndices.delete(index);input.closest('article').classList.toggle('selected',input.checked);this.updateBulkAction();});
    this.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>this.openEditor(Number(b.dataset.edit)));
    this.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>this.remove([Number(b.dataset.delete)]));
    this.querySelectorAll('[data-config-yaml]').forEach(button=>button.onclick=()=>this.openConfigurationEditor());
    this.querySelector('.connection-badge').onclick=()=>this.openConnectionDetails(entry);
    this.updateBulkAction();
    this.syncMenuButtons();
  }
  entityCards(entry){const type=this.type||TYPES[0],items=entry.entities[type];if(!items.length)return `<div class="empty small"><ha-icon icon="mdi:playlist-plus"></ha-icon><h3>${this.t('empty')}</h3><p>${this.t('empty_help')}</p></div>`;return items.map((item,i)=>{const entityId=entry.entity_ids?.[type]?.[i],selected=this.selectedIndices.has(i);return `<article class="${selected?'selected':''}"><label class="entity-select" title="${this.bt('select_entity')}"><input type="checkbox" data-select="${i}" aria-label="${this.bt('select_entity')}" ${selected?'checked':''}><span></span></label><div class="entity-icon"><ha-icon icon="mdi:${this.icon(type)}"></ha-icon></div><div class="details"><b>${this.escape(item.name||item.address||item.state_address||item.current_temperature_address||`${this.t('entity')} ${i+1}`)}</b><code>${this.escape(item.address||item.state_address||item.current_temperature_address||item.source_entity||'—')}</code><div>${this.chips(item,type)}</div></div>${entityId?`<span class="state-badge" data-entity-id="${this.escape(entityId)}" title="${this.escape(entityId)}">${this.escape(this.stateText(entityId))}</span>`:''}<button data-edit="${i}" class="icon-btn" title="${this.t('edit')}"><ha-icon icon="mdi:pencil"></ha-icon></button><button data-delete="${i}" class="icon-btn danger" title="${this.t('delete')}"><ha-icon icon="mdi:delete"></ha-icon></button></article>`;}).join('');}
  updateBulkAction(){const button=this.querySelector('#delete-selected');if(!button)return;const count=this.selectedIndices.size;button.hidden=!count;button.querySelector('span').textContent=`${this.bt('delete_selected')} (${count})`;}
  // Riepilogo compatto della card: niente booleani falsi, niente indirizzo duplicato,
  // ✓ per i flag attivi e valori "pretty" per device/state class.
  chips(item,type){
    const main=item.address||item.state_address||item.current_temperature_address||item.source_entity;
    const pretty=v=>String(v).split('_').map(w=>w?w.charAt(0).toUpperCase()+w.slice(1):w).join(' ');
    return Object.entries(item)
      .filter(([k,v])=>k!=='name'&&k!=='uid'&&v!==false&&v!==''&&!(typeof v==='string'&&v===main))
      .slice(0,5)
      .map(([k,v])=>{
        const label=this.escape(this.flowText(type,item,k,'data')||this.t(`fields.${k}`));
        if(v===true)return `<span class="chip-flag">✓ ${label}</span>`;
        const shown=(k==='device_class'||k==='state_class')?pretty(v):String(v);
        return `<span>${label}: ${this.escape(shown)}</span>`;
      }).join('');
  }
  stateText(entityId){const state=this._hass?.states?.[entityId];if(!state)return '—';const unit=state.attributes?.unit_of_measurement;return unit?`${state.state} ${unit}`:state.state;}
  updateStates(){this.querySelectorAll('.state-badge[data-entity-id]').forEach(el=>{const text=this.stateText(el.dataset.entityId);if(el.textContent!==text)el.textContent=text;});}
  inferred(item,type){const copy={...item};if(type==='covers')copy.cover_mode=item.position_state_address?'position':'traditional';if(type==='climates')copy.control_mode=item.control_mode||(item.target_temperature_address?'setpoint':'direct');if(type==='switches'||type==='lights')copy.control_behavior=CONTROL_MODE_FROM_ENTITY(item);if(type==='lights'){copy.light_mode=LIGHT_MODE_FROM_ENTITY(item);if(copy.light_mode==='dimmable'&&copy.brightness_scale==null)copy.brightness_scale=255;}return copy;}
  flowStep(type,item){if(type==='covers')return item.cover_mode==='position'?'covers_position':'covers_traditional';if(type==='climates')return item.control_mode==='direct'?'climates_direct':'climates_setpoint';return type;}
  flowText(type,item,key,section){const primary=this.flowStep(type,item),alternates=type==='covers'?['covers_traditional','covers_position']:type==='climates'?['climates_direct','climates_setpoint']:[];for(const step of [primary,...alternates]){const text=this.flowTranslations?.options?.step?.[step]?.[section]?.[key];if(text)return text;}}
  flowError(key){return this.flowTranslations?.options?.error?.[key]??key;}
  connectionLabel(key){for(const root of ['options','config'])for(const step of ['connection','user','rack_slot','tsap']){const label=this.flowTranslations?.[root]?.step?.[step]?.data?.[key];if(label)return label;}return key.split('_').map(word=>word.charAt(0).toUpperCase()+word.slice(1)).join(' ');}
  connectionDetailLabel(key){return this.t(`connection_detail_labels.${key}`)!==`connection_detail_labels.${key}`?this.t(`connection_detail_labels.${key}`):this.connectionLabel(key);}
  connectionValue(value){if(typeof value==='boolean')return this.t(value?'yes':'no');if(value===null||value===undefined||value==='')return '—';const translated=this.t(`connection_values.${value}`);return translated===`connection_values.${value}`?String(value):translated;}
  connectionState(entry){return entry.connection_entity_id?this._hass?.states?.[entry.connection_entity_id]:undefined;}
  connectionStatus(entry){return LIVE_CONNECTION_STATUS(this.connectionState(entry),entry.connected);}
  connectionBadgeAriaLabel(status){return `${this.t(status)} · ${this.t('connection_details_help')}`;}
  connectionBadgeContent(status){return `<span class="connection-badge-state">${this.t(status)}</span><ha-icon icon="mdi:information-outline"></ha-icon><span class="connection-badge-details">${this.t('connection_details_title')}</span>`;}
  formatDuration(milliseconds){if(milliseconds===null||milliseconds===undefined)return '—';let seconds=Math.max(0,Math.floor(milliseconds/1000)),days=Math.floor(seconds/86400);seconds%=86400;const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60);return [days?`${days}${this.t('availability.day_short')}`:'',hours?`${hours}${this.t('availability.hour_short')}`:'',(!days&&minutes)||(!days&&!hours)?`${minutes}${this.t('availability.minute_short')}`:''].filter(Boolean).join(' ');}
  availabilityMarkup(result){const label=state=>this.t(`availability.${state}`),timeline=result.intervals.map(interval=>{const width=(interval.end-interval.start)/CONNECTION_WINDOW_MS*100,title=`${label(interval.state)} · ${this.formatDuration(interval.end-interval.start)}`;return `<span tabindex="0" class="timeline-segment ${interval.state}" style="width:${width}%" title="${this.escape(title)}" aria-label="${this.escape(title)}"></span>`;}).join(''),last=result.lastDisconnection,unknown=result.durations.unknown,downtime=result.currentDurationState==="disconnected",durationLabel=this.t(`availability.${downtime?'current_downtime':'current_uptime'}`),duration=downtime?result.currentDowntime:result.currentUptime;return `<section class="availability"><div class="availability-title"><b>${this.t('availability.title')}</b><small>${this.t('availability.last_24_hours')}</small></div><div class="connection-timeline" role="group" aria-label="${this.t('availability.timeline_label')}">${timeline}</div><div class="timeline-labels"><span>${this.t('availability.hours_ago')}</span><span>${this.t('availability.now')}</span></div><dl class="availability-stats"><div><dt>${this.t('availability.percentage')}</dt><dd>${result.availability===null?'—':`${result.availability.toFixed(1)}%`}</dd></div><div><dt>${durationLabel}</dt><dd>${this.formatDuration(duration)}</dd></div><div><dt>${this.t('availability.disconnections')}</dt><dd>${result.disconnects}</dd></div><div><dt>${this.t('availability.unknown_time')}</dt><dd>${this.formatDuration(unknown)}</dd></div></dl>${last?`<p class="last-disconnection"><b>${this.t('availability.last_disconnection')}</b><span>${new Intl.DateTimeFormat(this.language,{dateStyle:'short',timeStyle:'short'}).format(last.start)} · ${this.formatDuration(last.end-last.start)}</span></p>`:''}<small class="availability-note">${this.t('availability.percentage_note')}</small></section>`;}
  liveAvailabilityFallback(connectionState,now){const status=CONNECTION_STATE(connectionState?.state),changed=Date.parse(connectionState?.last_changed),hasDuration=(status==="connected"||status==="disconnected")&&Number.isFinite(changed);return `${hasDuration?`<dl class="availability-stats availability-stats-live"><div><dt>${this.t(`availability.${status==="connected"?'current_uptime':'current_downtime'}`)}</dt><dd>${this.formatDuration(now-changed)}</dd></div></dl>`:''}<p class="history-unavailable">${this.t('availability.history_unavailable')}</p>`;}
  async loadConnectionAvailability(dialog,entry){const container=dialog.querySelector('.availability-container'),entityId=entry.connection_entity_id,connectionState=this.connectionState(entry),now=Date.now();if(!entityId){container.innerHTML=this.liveAvailabilityFallback(connectionState,now);return;}try{const start=new Date(now-CONNECTION_WINDOW_MS).toISOString(),end=new Date(now).toISOString(),path=`history/period/${encodeURIComponent(start)}?filter_entity_id=${encodeURIComponent(entityId)}&end_time=${encodeURIComponent(end)}&minimal_response&no_attributes`;const response=await this._hass.callApi('GET',path),history=Array.isArray(response?.[0])?response[0]:[];if(!history.length)throw Error('empty history');const result=BUILD_CONNECTION_AVAILABILITY(history,now);container.innerHTML=this.availabilityMarkup(APPLY_LIVE_CONNECTION_DURATION(result,connectionState,now));}catch(err){console.debug('Unable to load S7 PLC connection history',err);container.innerHTML=this.liveAvailabilityFallback(connectionState,now);}}
  openConnectionDetails(entry){
    const dialog=document.createElement('ha-dialog'),data=entry.data||{},{host,port}=data;
    const groups=connectionDetailGroups(data).map(group=>`<section class="connection-detail-group"><h3><ha-icon icon="${group.icon}"></ha-icon>${this.t(`connection_detail_sections.${group.key}`)}</h3><dl>${group.fields.map(({key,value})=>`<div class="connection-detail"><dt>${this.escape(this.connectionDetailLabel(key))}</dt><dd${key==='local_tsap'||key==='remote_tsap'?' class="technical-value"':''}>${this.escape(this.connectionValue(value))}</dd></div>`).join('')}</dl></section>`).join('');
    dialog.open=true;dialog.headerTitle=this.t('connection_details_title');dialog.style.setProperty('--mdc-dialog-max-width','min(560px,95vw)');dialog.style.setProperty('--mdc-dialog-min-width','min(480px,95vw)');dialog.style.setProperty('--dialog-content-padding','0');
    const status=this.connectionStatus(entry);
    dialog.innerHTML=`<style>${this.dialogStyles}</style><div class="dialog-body connection-details"><div class="connection-head"><div class="connection-head-text"><b>${this.escape(entry.title)}</b><code>${this.escape(host??'—')}${port!==undefined&&port!==null&&port!==''?`:${this.escape(port)}`:''}</code></div><span class="connection-status ${status}">${this.t(status)}</span></div><p>${this.t('connection_details_description')}</p><div class="availability-container"><div class="history-loading" role="status"><span></span>${this.t('availability.loading')}</div></div><div class="connection-detail-groups">${groups}</div></div><ha-dialog-footer slot="footer"><ha-button slot="primaryAction" appearance="accent">${this.t('close')}</ha-button></ha-dialog-footer>`;
    document.body.appendChild(dialog);this.loadConnectionAvailability(dialog,entry);dialog.addEventListener('closed',()=>dialog.remove());dialog.querySelector('[slot=primaryAction]').onclick=()=>{dialog.open=false;};
  }
  field([key,_label,kind='text',required=false,choices],item,type){const label=this.flowText(type,item,key,'data')||this.t(`fields.${key}`),description=this.flowText(type,item,key,'data_description'),help=description?`<small>${this.escape(description)}</small>`:'',value=(key in item)?(item[key]??''):(CLIMATE_PRESET_CORE_DEFAULTS[key]??CLIMATE_STATUS_CORE_DEFAULTS[key]??''),address=key.includes('address')||key==='source_entity',boolAddress=BOOL_FIELDS[type]?.includes(key),stringAddress=STRING_FIELDS[type]?.includes(key),placeholder=address?this.t(boolAddress?'address_example_bool':stringAddress?'address_example_string':'address_example'):key==='name'?this.t('name_example'):'',presetValue=key.startsWith('preset_mode_')&&key.endsWith('_value');if(kind==='light'){const option=(mode,icon,title,detail)=>`<label class="control-card" data-light-option="${mode}"><input type="radio" name="light_mode" value="${mode}" ${value===mode?'checked':''}><ha-icon icon="mdi:${icon}"></ha-icon><span><b>${this.t(title)}</b><small>${this.t(detail)}</small></span></label>`;return `<fieldset class="control-selector light-selector" data-field="light_mode"><legend>${this.t('light_ui.label')}</legend><div class="control-options light-options">${option('on_off','lightbulb-outline','light_ui.on_off_title','light_ui.on_off_description')}${option('dimmable','brightness-6','light_ui.dimmable_title','light_ui.dimmable_description')}</div></fieldset>`;}if(kind==='control'){const option=(mode,icon,title,detail)=>`<label class="control-card" data-control-option="${mode}"><input type="radio" name="control_behavior" value="${mode}" ${value===mode?'checked':''}><ha-icon icon="mdi:${icon}"></ha-icon><span><b>${this.t(title)}</b><small>${this.t(detail)}</small>${mode==='sync'?`<small class="sync-disabled-help">${this.t('control_ui.sync_requires_different')}</small>`:''}</span></label>`;return `<fieldset class="control-selector" data-field="control_behavior"><legend>${this.t('control_ui.label')}</legend><div class="control-options">${option('direct','toggle-switch-outline','control_ui.direct_title','control_ui.direct_description')}${option('sync','sync','control_ui.sync_title','control_ui.sync_description')}${option('pulse','gesture-tap-button','control_ui.pulse_title','control_ui.pulse_description')}</div></fieldset>`;}if(kind==='checkbox')return `<label class="check" data-field="${key}"><span><b>${this.escape(label)}</b>${help||`<small>${this.t('enabled_help')}</small>`}</span><input name="${key}" type="checkbox" ${value?'checked':''}></label>`;const caption=`<span class="field-label">${this.escape(label)}${required?`<em>${this.t('required')}</em>`:''}</span>`;if(key==='source_entity'){const states=this._hass?.states||{},ids=Object.keys(states).sort();return `<label data-field="source_entity">${caption}<input name="source_entity" class="mono" list="s7plc-entity-list" value="${this.escape(value)}" placeholder="${this.t('entity_example')}" autocomplete="off" ${required?'required':''}><datalist id="s7plc-entity-list">${ids.map(id=>`<option value="${this.escape(id)}">${this.escape(states[id]?.attributes?.friendly_name||'')}</option>`).join('')}</datalist>${help}</label>`;}if(key==='area'){const areas=Object.values(this._hass?.areas||{}).sort((a,b)=>(a.name||'').localeCompare(b.name||''));const known=areas.some(a=>a.area_id===value);return `<label data-field="area">${caption}<select name="area"><option value="" ${value?'':'selected'}>${this.t('no_area')}</option>${areas.map(a=>`<option value="${this.escape(a.area_id)}" ${a.area_id===value?'selected':''}>${this.escape(a.name)}</option>`).join('')}${value&&!known?`<option value="${this.escape(value)}" selected>${this.escape(value)}</option>`:''}</select>${help}</label>`;}if(key==='device_class'||key==='state_class'){const entry=this.entries.find(e=>e.entry_id===this.entryId),opts=key==='state_class'?entry?.selector_options?.state_classes||[]:entry?.selector_options?.device_classes?.[this.type||TYPES[0]]||[],pretty=v=>v.split('_').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' '),known=opts.includes(value);return `<label data-field="${key}">${caption}<select name="${key}"><option value="" ${value?'':'selected'}>${this.t('none_option')}</option>${opts.map(v=>`<option value="${this.escape(v)}" ${v===value?'selected':''}>${this.escape(pretty(v))}</option>`).join('')}${value&&!known?`<option value="${this.escape(value)}" selected>${this.escape(value)}</option>`:''}</select>${help}</label>`;}if(kind==='select')return `<label data-field="${key}">${caption}<select name="${key}" ${required?'required':''}>${Object.keys(choices).map(v=>`<option value="${v}" ${v===value?'selected':''}>${this.t(`choices.${v}`)}</option>`).join('')}</select>${help}</label>`;return `<label data-field="${key}">${caption}<input name="${key}" type="${kind}" class="${address?'mono':''}" value="${this.escape(value)}" placeholder="${placeholder}" ${kind==='number'?(presetValue?'step="1"':key==='brightness_scale'?'step="1" min="1" max="65535"':'step="any"'):''} ${required?'required':''}>${help}</label>`;}
  editorSections(type,item){const fields=FIELDS[type],byKeys=keys=>keys.map(key=>fields.find(field=>field[0]===key)).filter(Boolean),isAddress=f=>f[0].includes('address')||f[0]==='source_entity'||f[0]==='cover_mode'||f[0]==='control_mode',isIdentity=f=>['name','area','scan_interval'].includes(f[0]),section=(icon,title,description,list,key='')=>list.length?`<section class="form-section" ${key?`data-section="${key}"`:''}><div class="section-head"><span class="section-icon"><ha-icon icon="mdi:${icon}"></ha-icon></span><div><b>${title}</b><small>${description}</small></div></div><div class="field-grid">${list.map(f=>this.field(f,item,type)).join('')}</div></section>`:'';
    if(type==='switches')return section('tune-variant',this.t('command_behavior'),this.t('command_behavior_help'),byKeys(['control_behavior']),'command')+section('connection',this.t('plc_connection'),this.t('plc_connection_help'),byKeys(['state_address','command_address']),'addresses')+section('cog-outline',this.t('options_section'),this.t('options_section_help'),byKeys(['pulse_duration']),'options')+section('card-account-details-outline',this.t('ha_details'),this.t('ha_details_help'),byKeys(['name','area','scan_interval']),'ha');
    if(type==='lights')return section('tune-variant',this.t('command_behavior'),this.t('command_behavior_help'),byKeys(['control_behavior']),'command')+section('lightbulb-outline',this.t('light_ui.section_title'),this.t('light_ui.section_help'),byKeys(['light_mode']),'light-mode')+section('connection',this.t('plc_connection'),this.t('plc_connection_help'),byKeys(['state_address','command_address','brightness_state_address','brightness_command_address']),'addresses')+section('cog-outline',this.t('options_section'),this.t('options_section_help'),byKeys(['pulse_duration','brightness_scale']),'options')+section('card-account-details-outline',this.t('ha_details'),this.t('ha_details_help'),byKeys(['name','area','scan_interval']),'ha');
    return section('connection',this.t('plc_connection'),this.t('plc_connection_help'),fields.filter(isAddress))+section('tune-variant',this.t('behavior'),this.t('behavior_help'),fields.filter(f=>!isAddress(f)&&!isIdentity(f)))+section('card-account-details-outline',this.t('ha_details'),this.t('ha_details_help'),fields.filter(isIdentity));}
  openEditor(index=null){const entry=this.entries.find(e=>e.entry_id===this.entryId),type=this.type||TYPES[0],raw=index===null?{}:entry.entities[type][index],initial=this.inferred(raw,type),dialog=document.createElement('ha-dialog');dialog.open=true;dialog.headerTitle=index===null?this.t('new_entity'):this.t('edit_entity');dialog.style.setProperty('--mdc-dialog-max-width','min(940px,95vw)');dialog.style.setProperty('--mdc-dialog-min-width','min(940px,95vw)');dialog.style.setProperty('--dialog-content-padding','0');dialog.innerHTML=`<style>${this.dialogStyles}</style><div class="dialog-body"><div class="editor-intro"><span class="editor-type-icon"><ha-icon icon="mdi:${this.icon(type)}"></ha-icon></span><div><span class="eyebrow">${this.t(`types.${type}`)}</span><h3>${index===null?this.t('configure_new'):this.t('update_configuration')}</h3><p>${this.t('save_help')}</p></div></div><div class="mode-tabs" role="tablist" aria-label="${this.t('editor_mode')}"><button class="active" data-mode="visual" role="tab"><ha-icon icon="mdi:form-select"></ha-icon><span>${this.t('visual_editor')}<small>${this.t('guided')}</small></span></button><button data-mode="yaml" role="tab"><ha-icon icon="mdi:code-braces"></ha-icon><span>YAML<small>${this.t('advanced')}</small></span></button></div><form class="visual-form">${this.editorSections(type,initial)}</form><div class="yaml-editor" style="display:none"><ha-alert alert-type="warning">${this.t('yaml_warning')}</ha-alert><textarea spellcheck="false" aria-label="${this.t('yaml_label')}">${this.escape(this.toYaml(raw))}</textarea></div><ha-alert class="editor-error" alert-type="error" style="display:none"></ha-alert></div><ha-dialog-footer slot="footer"><ha-button slot="secondaryAction" appearance="plain">${this.t('cancel')}</ha-button><ha-button slot="primaryAction" appearance="accent">${this.t('save')}</ha-button></ha-dialog-footer>`;document.body.appendChild(dialog);
    const form=dialog.querySelector('form');
    // Mostra solo i campi pertinenti alla modalità scelta (tapparelle/clima)
    const syncMode=()=>{const sel=form.elements.cover_mode||form.elements.control_mode;if(!sel)return;let hidden=MODE_HIDDEN[type]?.[sel.value]||[];if(type==='covers'){const statusAddr=form.elements.cover_status_address?.value.trim();if(!statusAddr){hidden=[...hidden,...COVER_STATUS_VALUE_FIELDS];}if(sel.value==='position'&&!form.elements.tilt_state_address?.value.trim()){hidden=[...hidden,...COVER_TILT_INVERT_FIELDS];}}if(type==='climates'&&sel.value==='setpoint'){if(!form.elements.preset_mode_address?.value.trim()){hidden=[...hidden,'preset_mode_bidirectional'];}if(!form.elements.hvac_status_address?.value.trim()){hidden=[...hidden,...CLIMATE_STATUS_VALUE_FIELDS];}}form.querySelectorAll('[data-field]').forEach(l=>l.classList.toggle('hidden-field',hidden.includes(l.dataset.field)));};
    const updateControlBehavior=()=>{if(type!=='switches'&&type!=='lights')return;const state=form.elements.state_address.value.trim(),command=form.elements.command_address.value.trim(),sync=form.querySelector('input[name="control_behavior"][value="sync"]'),canSync=Boolean(command)&&command!==state;sync.disabled=!canSync;sync.closest('.control-card').classList.toggle('disabled',!canSync);if(!canSync&&sync.checked)form.querySelector('input[name="control_behavior"][value="direct"]').checked=true;const selected=form.querySelector('input[name="control_behavior"]:checked')?.value||'direct';form.querySelector('[data-field="pulse_duration"]').classList.toggle('hidden-field',selected!=='pulse');updateOptionsSection();};
    const updateOptionsSection=()=>{const section=form.querySelector('[data-section="options"]');if(section)section.classList.toggle('hidden-field',![...section.querySelectorAll('[data-field]')].some(field=>!field.classList.contains('hidden-field')));};
    const updateLightMode=()=>{if(type!=='lights')return;const dimmable=form.querySelector('input[name="light_mode"]:checked')?.value==='dimmable';['brightness_state_address','brightness_command_address','brightness_scale'].forEach(key=>form.querySelector(`[data-field="${key}"]`).classList.toggle('hidden-field',!dimmable));if(dimmable&&!form.elements.brightness_scale.value)form.elements.brightness_scale.value='255';updateOptionsSection();};
    syncMode();updateLightMode();updateControlBehavior();['cover_mode','control_mode'].forEach(k=>{if(form.elements[k])form.elements[k].onchange=syncMode;});
    if(form.elements.control_behavior)form.querySelectorAll('input[name="control_behavior"]').forEach(input=>input.onchange=updateControlBehavior);
    if(form.elements.light_mode)form.querySelectorAll('input[name="light_mode"]').forEach(input=>input.onchange=updateLightMode);
    if(form.elements.state_address)form.elements.state_address.addEventListener('input',updateControlBehavior);
    if(form.elements.command_address)form.elements.command_address.addEventListener('input',updateControlBehavior);
    if(form.elements.cover_status_address)form.elements.cover_status_address.oninput=syncMode;
    if(form.elements.tilt_state_address)form.elements.tilt_state_address.oninput=syncMode;
    if(form.elements.preset_mode_address)form.elements.preset_mode_address.oninput=syncMode;
    if(form.elements.hvac_status_address)form.elements.hvac_status_address.oninput=syncMode;
    let mode='visual';dialog.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;dialog.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));dialog.querySelector('.visual-form').style.display=mode==='visual'?'flex':'none';dialog.querySelector('.yaml-editor').style.display=mode==='yaml'?'block':'none';});dialog.querySelector('[slot=secondaryAction]').onclick=()=>{dialog.open=false;};dialog.addEventListener('closed',()=>dialog.remove());dialog.querySelector('[slot=primaryAction]').onclick=async()=>{const alert=dialog.querySelector('.editor-error');try{const msg={type:"s7plc/config/save_entity",entry_id:this.entryId,entity_type:type,index};if(mode==='yaml')msg.entity_yaml=dialog.querySelector('textarea').value;else msg.entity=this.formEntity(form,raw,type);await this._hass.callWS(msg);dialog.open=false;this._loaded=false;await this.load();}catch(err){const message=err.message||String(err);alert.textContent=this.flowError(message);alert.style.display='block';alert.scrollIntoView({behavior:'smooth',block:'nearest'});}};
  }

  formEntity(form,original,type){if(!form.reportValidity())throw Error(this.t('required_error'));const entity={...original};for(const field of FIELDS[type]){const [key,,,required]=field;if(key==='control_behavior'||key==='light_mode')continue;const input=form.elements[key];let value=input.type==='checkbox'?input.checked:input.value.trim();if(key==='cover_mode'||key==='control_mode')continue;if(input.type==='number'&&value!=='')value=Number(value);const presetModeValue=key.startsWith('preset_mode_')&&key.endsWith('_value'),statusCoreValue=key in CLIMATE_STATUS_CORE_DEFAULTS;if(value===''&&!required){if(presetModeValue)entity[key]=null;else if(statusCoreValue)entity[key]='';else delete entity[key];}else entity[key]=value;}if(type==='switches'||type==='lights')Object.assign(entity,APPLY_CONTROL_MODE({},form.elements.control_behavior.value));if(type==='lights'){const lightMode=form.elements.light_mode.value;delete entity.light_mode;if(lightMode==='on_off'){delete entity.brightness_state_address;delete entity.brightness_command_address;delete entity.brightness_scale;}else{if(!entity.brightness_state_address)throw Error(this.t('brightness_state_required_error'));if(entity.brightness_scale==null)entity.brightness_scale=255;if(entity.brightness_scale<1||entity.brightness_scale>65535)throw Error(this.t('brightness_scale_error'));}}const mode=form.elements.cover_mode?.value;if(type==='covers'){MODE_HIDDEN.covers[mode].forEach(k=>delete entity[k]);if(mode==='position'&&!entity.tilt_state_address){COVER_TILT_INVERT_FIELDS.forEach(k=>delete entity[k]);}const needed=mode==='position'?'position_state_address':'open_command_address';if(!entity[needed]||(mode==='traditional'&&!entity.close_command_address))throw Error(this.t('cover_required_error'));}if(type==='climates'){entity.control_mode=form.elements.control_mode.value;MODE_HIDDEN.climates[entity.control_mode].forEach(k=>delete entity[k]);if(entity.control_mode==='setpoint'&&!entity.target_temperature_address)throw Error(this.t('climate_required_error'));}return entity;}
  toYaml(obj){return Object.entries(obj).map(([k,v])=>`${k}: ${JSON.stringify(v)}`).join('\n');}
  async openConfigurationEditor(){
    const entry=this.entries.find(e=>e.entry_id===this.entryId),dialog=document.createElement('ha-dialog');
    let canonical='',loadError='';
    try{canonical=(await this._hass.callWS({type:'s7plc/config/get_configuration',entry_id:this.entryId})).configuration_yaml||'';}catch(err){loadError=`${this.t('configuration_load_error')} ${err.message||String(err)}`;}
    dialog.open=true;dialog.headerTitle=this.t('configuration_yaml_title');dialog.style.setProperty('--mdc-dialog-max-width','min(1000px,96vw)');dialog.style.setProperty('--mdc-dialog-min-width','min(900px,96vw)');dialog.style.setProperty('--dialog-content-padding','0');
    dialog.innerHTML=`<style>${this.dialogStyles}</style><div class="dialog-body configuration-editor"><ha-alert alert-type="warning">${this.t('configuration_yaml_warning')}</ha-alert><div class="configuration-tools"><button id="yaml-import"><ha-icon icon="mdi:upload"></ha-icon>${this.t('import_yaml')}</button><button id="yaml-export"><ha-icon icon="mdi:download"></ha-icon>${this.t('export_current_yaml')}</button><button id="yaml-backup"><ha-icon icon="mdi:database-export-outline"></ha-icon>${this.t('download_backup')}</button><input id="yaml-file" type="file" accept=".yaml,.yml,text/yaml,application/yaml" hidden></div><textarea spellcheck="false" aria-label="${this.t('configuration_yaml')}">${this.escape(canonical)}</textarea><ha-alert class="editor-error" alert-type="error" style="display:none"></ha-alert></div><ha-dialog-footer slot="footer"><ha-button slot="secondaryAction" appearance="plain">${this.t('cancel')}</ha-button><ha-button slot="primaryAction" appearance="accent">${this.t('save')}</ha-button></ha-dialog-footer>`;
    document.body.appendChild(dialog);const textarea=dialog.querySelector('textarea'),file=dialog.querySelector('#yaml-file'),alert=dialog.querySelector('.editor-error'),saveButton=dialog.querySelector('[slot=primaryAction]'),backupButton=dialog.querySelector('#yaml-backup');
    const showError=message=>{alert.textContent=message;alert.style.display='block';alert.scrollIntoView({behavior:'smooth',block:'nearest'});};
    textarea.disabled=!!loadError;saveButton.disabled=!!loadError;dialog.querySelector('#yaml-import').disabled=!!loadError;dialog.querySelector('#yaml-export').disabled=!!loadError;backupButton.disabled=!!loadError;if(loadError)showError(loadError);
    dialog.querySelector('#yaml-import').onclick=()=>file.click();file.onchange=async()=>{if(file.files[0])textarea.value=await file.files[0].text();file.value='';};
    const download=(contents,suffix)=>{const blob=new Blob([contents],{type:'application/yaml;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`${(entry.title||'s7plc').replace(/[^a-z0-9_-]+/gi,'-').toLowerCase()}-${suffix}.yaml`;link.click();URL.revokeObjectURL(url);};
    dialog.querySelector('#yaml-export').onclick=()=>download(textarea.value,'config');
    let backupLoading=false;backupButton.onclick=async()=>{if(backupLoading)return;backupLoading=true;backupButton.disabled=true;alert.style.display='none';try{const backup=await this._hass.callWS({type:'s7plc/config/get_configuration',entry_id:this.entryId});download(backup.configuration_yaml,'backup');}catch(err){showError(`${this.t('configuration_download_error')} ${err.message||String(err)}`);}finally{backupLoading=false;backupButton.disabled=false;}};
    dialog.querySelector('[slot=secondaryAction]').onclick=()=>{dialog.open=false;};dialog.addEventListener('closed',()=>dialog.remove());
    let saveLoading=false;saveButton.onclick=async()=>{if(saveLoading)return;saveLoading=true;saveButton.disabled=true;alert.style.display='none';try{await this._hass.callWS({type:'s7plc/config/save_configuration',entry_id:this.entryId,configuration_yaml:textarea.value});dialog.open=false;this.selectedIndices.clear();this._loaded=false;await this.load();}catch(err){let message=err.message||String(err);if(err.code==='invalid_configuration_entity'){try{const detail=JSON.parse(message),type=this.t(`types.${detail.entity_type}`);message=`${type} #${detail.index+1}: ${this.flowError(detail.error_key)}`;}catch(parseError){console.warn('Invalid structured configuration error',parseError);}}showError(message);}finally{saveLoading=false;saveButton.disabled=false;}};
  }
  // Conferma di eliminazione con ha-dialog, coerente con lo stile di Home Assistant
  remove(indices){
    const sorted=[...new Set(indices)].sort((a,b)=>b-a);
    if(!sorted.length)return;
    const dialog=document.createElement('ha-dialog');
    dialog.open=true;dialog.headerTitle=this.t('delete_title');
    const confirmation=sorted.length===1?this.t('delete_confirm'):this.bt('delete_selected_confirm',{count:sorted.length});
    dialog.innerHTML=`<div style="padding:0 24px 8px;font-family:var(--ha-font-family-body,Roboto,sans-serif);color:var(--primary-text-color);max-width:420px">${confirmation}</div><ha-dialog-footer slot="footer"><ha-button slot="secondaryAction" appearance="plain">${this.t('cancel')}</ha-button><ha-button slot="primaryAction" appearance="accent" style="--mdc-theme-primary:var(--error-color);--ha-button-accent-bg:var(--error-color)">${this.t('delete')}</ha-button></ha-dialog-footer>`;
    document.body.appendChild(dialog);
    dialog.addEventListener('closed',()=>dialog.remove());
    dialog.querySelector('[slot=secondaryAction]').onclick=()=>{dialog.open=false;};
    dialog.querySelector('[slot=primaryAction]').onclick=async()=>{
      dialog.open=false;
      for(const index of sorted)await this._hass.callWS({type:"s7plc/config/delete_entity",entry_id:this.entryId,entity_type:this.type||TYPES[0],index});
      this.selectedIndices.clear();
      this._loaded=false;await this.load();
    };
  }
  icon(t){return({sensors:'gauge',binary_sensors:'checkbox-marked-circle',switches:'toggle-switch',covers:'window-shutter',lights:'lightbulb',buttons:'gesture-tap-button',numbers:'numeric',texts:'form-textbox',climates:'thermostat',entity_sync:'sync'})[t];} escape(v){const d=document.createElement('div');d.textContent=v??'';return d.innerHTML;}
  get styles(){return `
:host{display:block;background:var(--primary-background-color);min-height:100vh;color:var(--primary-text-color);font-family:var(--ha-font-family-body,Roboto,sans-serif);-webkit-font-smoothing:antialiased}
button,input,select,textarea,ha-button{font-family:inherit}
.page{max-width:1180px;margin:auto;padding:32px 24px 64px}
.hero-banner{width:100%;margin:0 0 18px;border-radius:18px;overflow:hidden;background:#03182f;box-shadow:0 8px 28px #00000018}
.hero-banner img{display:block;width:100%;height:auto}
header,.toolbar,.summary,article{display:flex;align-items:center}
.mobile-controls{display:none}
.mobile-actions,.summary-actions{display:flex;align-items:center;gap:10px;min-width:0}
.integration-version{color:var(--secondary-text-color);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap;padding:5px 11px;border:1px solid var(--divider-color);border-radius:99px;background:var(--card-background-color)}
.config-yaml{display:flex;align-items:center;gap:7px;white-space:nowrap;border:1px solid var(--divider-color)}.config-yaml ha-icon{--mdc-icon-size:18px}
.menubar{padding:8px 4px}
ha-menu-button{color:var(--primary-text-color)}
h2,p{margin:0}
h2{font-size:19px;font-weight:600;letter-spacing:-.01em}
.toolbar p{color:var(--secondary-text-color);font-size:14px}
select,input{box-sizing:border-box;padding:11px 13px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);color:inherit;font:inherit;font-size:14px;transition:border-color .15s,box-shadow .15s}
select:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color))}
select:focus,input:focus{outline:0;border-color:var(--primary-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--primary-color) 16%,transparent)}
.summary{position:relative;overflow:hidden;margin:0 0 18px;padding:22px 26px;background:linear-gradient(125deg,color-mix(in srgb,var(--primary-color) 90%,black),color-mix(in srgb,var(--primary-color) 58%,var(--accent-color)));color:#fff;border-radius:20px;gap:20px;justify-content:space-between;box-shadow:0 12px 32px color-mix(in srgb,var(--primary-color) 28%,transparent)}
.summary::before{content:'';position:absolute;inset:0;background:radial-gradient(560px 220px at 88% -30%,#ffffff2e,transparent 65%),radial-gradient(320px 180px at 6% 130%,#ffffff14,transparent 70%);pointer-events:none}
.summary-info>ha-icon{--mdc-icon-size:26px;position:relative;display:grid;place-items:center;width:54px;height:54px;flex:0 0 auto;border-radius:16px;background:#ffffff24;box-shadow:inset 0 0 0 1px #ffffff30;backdrop-filter:blur(4px)}
.summary-info{position:relative;display:flex;align-items:center;gap:16px;min-width:0;flex:1 1 auto}
.summary .plc-details{display:flex;flex-direction:column;gap:4px;min-width:0}
.summary .plc-details>span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.summary .plc-details>span{opacity:.85;font-size:13.5px}
.summary .plc-title{display:flex;align-items:center;gap:10px;flex-wrap:wrap;opacity:1;font-size:15px}
.summary .plc-title b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.summary-actions{position:relative;flex:0 1 auto;justify-content:flex-end}
.summary-actions .config-yaml,
.summary-actions select,
.summary-actions .integration-version{color:#fff;background:#ffffff18;border-color:#ffffff30;box-shadow:none}
.summary-actions .config-yaml:hover,
.summary-actions select:hover{background:#ffffff26;border-color:#ffffff45}
.summary-actions .config-yaml:focus-visible,
.summary-actions select:focus{border-color:#ffffff70;box-shadow:0 0 0 3px #ffffff20}
.summary-actions select{min-width:120px;max-width:230px}
.summary-actions select option{color:var(--primary-text-color);background:var(--card-background-color)}
.summary-actions .integration-version{opacity:1}
.connection-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;background:#ffffff1f;box-shadow:inset 0 0 0 1px #ffffff2e;color:#fff;font-size:11px;font-weight:700;letter-spacing:.03em;line-height:1.5;transition:background .15s,transform .15s,box-shadow .15s}
.connection-badge:hover{background:#ffffff30;transform:translateY(-1px)}
.connection-badge:focus-visible{outline:2px solid #fff;outline-offset:2px;box-shadow:inset 0 0 0 1px #ffffff55,0 0 0 3px #ffffff25}
.connection-badge:active{background:#ffffff3d;transform:translateY(0)}
.connection-badge ha-icon{--mdc-icon-size:15px;margin-left:2px}.connection-badge-details{font-weight:500;letter-spacing:0;opacity:.92}
.connection-badge::before{content:'';width:7px;height:7px;border-radius:50%;background:#ff8a80;box-shadow:0 0 8px #ff8a80aa}
.connection-badge.connected::before{background:#69f0ae;box-shadow:0 0 8px #69f0aeaa;animation:s7pulse 2.4s ease-out infinite}
.connection-badge.unknown::before{background:#b0bec5;box-shadow:0 0 8px #b0bec599}
@keyframes s7pulse{0%{box-shadow:0 0 0 0 #69f0ae66}70%{box-shadow:0 0 0 6px transparent}100%{box-shadow:0 0 0 0 transparent}}
nav{display:flex;gap:8px;overflow:auto;padding:6px 2px 20px;scrollbar-width:thin}
button,.primary{border:0;border-radius:10px;padding:10px 13px;cursor:pointer;color:inherit;background:var(--card-background-color);font:inherit;font-size:13px}
button:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
nav button{white-space:nowrap;border:1px solid var(--divider-color);border-radius:99px;display:flex;align-items:center;gap:7px;padding:9px 16px;font-weight:500;transition:border-color .15s,background .15s,box-shadow .15s,transform .15s}
nav button ha-icon{--mdc-icon-size:17px;opacity:.7}
nav button:hover{border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color));transform:translateY(-1px)}
nav button.active{background:linear-gradient(135deg,var(--primary-color),color-mix(in srgb,var(--primary-color) 72%,var(--accent-color)));color:#fff;border-color:transparent;box-shadow:0 4px 12px color-mix(in srgb,var(--primary-color) 35%,transparent)}
nav button.active ha-icon{opacity:1}
nav span{margin-left:2px;font-variant-numeric:tabular-nums;font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;background:color-mix(in srgb,currentColor 12%,transparent)}
.toolbar{justify-content:space-between;margin:10px 0 18px;gap:12px}
.toolbar p{font-size:13px;margin-top:5px}
.toolbar-actions{display:flex;align-items:center;gap:8px}
.batch-delete{display:flex;align-items:center;gap:6px;border-radius:99px;padding:10px 16px;border:1px solid color-mix(in srgb,var(--error-color) 35%,var(--divider-color));background:var(--card-background-color)}
.batch-delete[hidden]{display:none}
.primary{background:linear-gradient(135deg,var(--primary-color),color-mix(in srgb,var(--primary-color) 72%,var(--accent-color)));color:#fff;font-weight:600;display:flex;align-items:center;gap:6px;border-radius:99px;padding:10px 18px;box-shadow:0 4px 14px color-mix(in srgb,var(--primary-color) 35%,transparent);transition:transform .15s,box-shadow .15s,filter .15s}
.primary:hover{transform:translateY(-1px);box-shadow:0 7px 20px color-mix(in srgb,var(--primary-color) 45%,transparent);filter:brightness(1.06)}
.primary:active{transform:translateY(0)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(440px,100%),1fr));gap:12px;align-items:start}
.cards .empty.small{grid-column:1/-1}
article{position:relative;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;margin:0;padding:15px;gap:12px;transition:border-color .15s,box-shadow .15s,transform .15s}
article::before{content:'';position:absolute;left:-1px;top:16px;bottom:16px;width:3px;border-radius:0 3px 3px 0;background:linear-gradient(var(--primary-color),color-mix(in srgb,var(--primary-color) 55%,var(--accent-color)));opacity:0;transition:opacity .15s}
article:hover{border-color:color-mix(in srgb,var(--primary-color) 40%,var(--divider-color));box-shadow:0 10px 26px #00000014;transform:translateY(-2px)}
article:hover::before{opacity:1}
article.selected{border-color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 6%,var(--card-background-color))}
article.selected::before{opacity:1}
.entity-select{display:grid;place-items:center;flex:0 0 auto;cursor:pointer}.entity-select input{position:absolute;opacity:0;pointer-events:none}.entity-select span{box-sizing:border-box;width:20px;height:20px;border:2px solid var(--secondary-text-color);border-radius:6px;display:grid;place-items:center;transition:border-color .15s,background .15s}.entity-select input:checked+span{border-color:var(--primary-color);background:var(--primary-color)}.entity-select input:checked+span::after{content:'✓';color:white;font-size:13px;font-weight:700;line-height:1}.entity-select input:focus-visible+span{outline:2px solid var(--primary-color);outline-offset:2px}
.entity-icon{display:grid;place-items:center;width:44px;height:44px;flex:0 0 auto;border-radius:13px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary-color) 18%,transparent),color-mix(in srgb,var(--primary-color) 8%,transparent));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary-color) 22%,transparent);color:var(--primary-color)}
.entity-icon ha-icon{--mdc-icon-size:21px}
.details{flex:1;min-width:0}.details>b,.details>code{display:block}
.details>b{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.details code{margin:4px 0 9px;color:var(--secondary-text-color);font-size:12px;font-family:ui-monospace,'SF Mono',Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.details span{font-size:11px;background:var(--secondary-background-color);padding:4px 9px;border-radius:99px;margin:2px 4px 2px 0;display:inline-block}
.details span.chip-flag{background:color-mix(in srgb,var(--primary-color) 12%,transparent);color:var(--primary-color);font-weight:600}
.state-badge{flex:0 0 auto;font-size:12px;font-weight:600;padding:5px 12px;border-radius:99px;background:color-mix(in srgb,var(--primary-color) 12%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary-color) 18%,transparent);color:var(--primary-color);white-space:nowrap;font-variant-numeric:tabular-nums;max-width:150px;overflow:hidden;text-overflow:ellipsis}
.icon-btn{width:38px;height:38px;padding:0;flex:0 0 auto;border-radius:99px;display:grid;place-items:center;background:transparent;transition:background .15s,transform .15s}
.icon-btn:hover{background:var(--secondary-background-color);transform:scale(1.05)}
.icon-btn ha-icon{--mdc-icon-size:19px}
.danger{color:var(--error-color)!important}
.danger:hover{background:color-mix(in srgb,var(--error-color) 10%,transparent)!important}
.danger:focus-visible{outline-color:var(--error-color)}
.empty{text-align:center;padding:18vh 20px}
.empty.small{padding:64px 20px;border:1.5px dashed var(--divider-color);border-radius:18px;background:color-mix(in srgb,var(--secondary-background-color) 35%,transparent)}
.empty ha-icon{--mdc-icon-size:52px;color:var(--secondary-text-color);opacity:.7}
.empty h2,.empty h3{margin:14px 0 6px}
.empty p{color:var(--secondary-text-color)}
.loading{padding:36px;color:var(--secondary-text-color)}
@media(prefers-reduced-motion:reduce){.page *,.page *::before{transition:none!important;animation:none!important}}
@media(max-width:650px){.page{padding:12px 12px 48px}.mobile-controls{display:flex;align-items:center;gap:8px;margin-bottom:12px;min-width:0}.mobile-actions{flex:1;justify-content:flex-end}.mobile-actions select{flex:1;min-width:0}.mobile-actions .config-yaml{flex:0 0 auto}.hero-banner{margin-bottom:12px;border-radius:14px}.summary{padding:18px;border-radius:16px}.summary-actions{display:none}.summary-info{gap:14px}.details div,.toolbar p{display:none}.toolbar{align-items:flex-start}.toolbar-actions{flex-wrap:wrap;justify-content:flex-end}.state-badge{display:none}}
@media(max-width:500px){.mobile-actions .integration-version{display:none}.mobile-actions .config-yaml span{display:none}}
@media(max-width:480px){.connection-badge-details{display:none}}
@media(min-width:651px) and (max-width:850px){.summary{padding:18px}.summary-actions{gap:7px}.summary-actions .integration-version{display:none}.summary-actions select{max-width:180px}}`;}
  get dialogStyles(){return `
.dialog-body{box-sizing:border-box;width:100%;max-height:min(76vh,860px);overflow:auto;padding:0 28px 28px;font-family:var(--ha-font-family-body,Roboto,sans-serif);color:var(--primary-text-color)}
.dialog-body button,.dialog-body input,.dialog-body select,.dialog-body textarea,ha-dialog-footer,ha-button{font-family:inherit}
.dialog-body h3,.dialog-body p{margin:0}
.dialog-body select,.dialog-body input:not([type=checkbox]){box-sizing:border-box;padding:11px 13px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);color:inherit;font:inherit;font-size:14px}
.dialog-body button{border:0;cursor:pointer;color:inherit;font:inherit;font-size:13px;background:transparent}
.dialog-body button:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.editor-intro{display:flex;align-items:center;gap:16px;padding:4px 2px 20px}
.editor-type-icon,.section-icon{display:grid;place-items:center;flex:0 0 auto;border-radius:14px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary-color) 18%,transparent),color-mix(in srgb,var(--primary-color) 8%,transparent));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary-color) 22%,transparent);color:var(--primary-color)}
.editor-type-icon{width:52px;height:52px}.editor-type-icon ha-icon{--mdc-icon-size:28px}
.editor-intro h3{font-size:18px;font-weight:600;letter-spacing:-.01em;margin:2px 0 4px}
.editor-intro p,.editor-intro .eyebrow,.section-head small,.visual-form label small{color:var(--secondary-text-color)}
.eyebrow{text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:.09em;color:var(--primary-color)!important}
.mode-tabs{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:24px;padding:5px;border-radius:99px;background:var(--secondary-background-color)}
.mode-tabs button{display:flex;text-align:left;align-items:center;justify-content:center;gap:9px;border:0;background:transparent;padding:9px 12px;border-radius:99px;transition:background .15s,box-shadow .15s,opacity .15s;opacity:.7}
.mode-tabs button.active{background:var(--card-background-color);box-shadow:0 2px 8px #00000026;opacity:1}
.mode-tabs button.active ha-icon{color:var(--primary-color)}
.mode-tabs button span,.mode-tabs button small{display:block}
.mode-tabs button small{font-size:10px;opacity:.72;margin-top:2px}
.visual-form{display:flex;flex-direction:column;gap:16px}
.form-section{border:1px solid var(--divider-color);border-radius:18px;padding:20px 22px;background:color-mix(in srgb,var(--secondary-background-color) 40%,transparent)}
.section-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.section-head b{display:block;font-size:14px;letter-spacing:-.01em}
.section-head small{display:block;font-size:11px;margin-top:2px}
.section-icon{width:36px;height:36px;border-radius:11px}.section-icon ha-icon{--mdc-icon-size:19px}
.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 18px}
.control-selector{grid-column:1/-1;border:0;padding:0;margin:0;min-width:0}.control-selector legend{font-size:13px;font-weight:600;margin-bottom:10px;padding:0}.control-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.light-options{grid-template-columns:repeat(2,minmax(0,1fr))}
.control-card{box-sizing:border-box;display:flex!important;flex-direction:column!important;align-items:flex-start;gap:10px!important;position:relative;min-height:172px;padding:16px!important;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color);cursor:pointer;transition:border-color .15s,box-shadow .15s,background .15s}.control-card:hover{border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color))}.control-card:has(input:checked){border-color:var(--primary-color);box-shadow:0 0 0 2px color-mix(in srgb,var(--primary-color) 18%,transparent);background:color-mix(in srgb,var(--primary-color) 5%,var(--card-background-color))}.control-card input{position:absolute;opacity:0;pointer-events:none}.control-card ha-icon{color:var(--primary-color);--mdc-icon-size:25px}.control-card span,.control-card b,.control-card small{display:block}.control-card b{font-size:13px}.control-card small{font-size:10.5px!important;line-height:1.45;margin-top:6px}.control-card.disabled{cursor:not-allowed;opacity:.48}.sync-disabled-help{display:none!important;color:var(--error-color)!important}.control-card.disabled .sync-disabled-help{display:block!important}
.light-options .control-card{min-height:110px;padding:12px 14px!important;gap:6px!important}
.light-options .control-card small{margin-top:3px}
.visual-form label:not(.check){display:flex;flex-direction:column;gap:8px;font-size:13px}
.visual-form input,.visual-form select{width:100%;background:var(--card-background-color);transition:border-color .15s,box-shadow .15s}
.visual-form input:hover,.visual-form select:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color))}
.visual-form input:focus,.visual-form select:focus{outline:0;border-color:var(--primary-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--primary-color) 16%,transparent)}
.visual-form input.mono{font-family:ui-monospace,'SF Mono',Consolas,monospace;font-size:13px;letter-spacing:.02em}
.field-label{display:flex;align-items:center;justify-content:space-between;font-weight:500}
.field-label em{font-size:9px;font-style:normal;text-transform:uppercase;letter-spacing:.06em;color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 12%,transparent);border-radius:99px;padding:3px 8px}
.visual-form label small{font-size:10.5px}
.visual-form .check{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px;padding:8px 14px;border-radius:13px;background:var(--card-background-color);border:1px solid var(--divider-color);cursor:pointer;transition:border-color .15s,box-shadow .15s}
.visual-form .check>span{min-width:0}
.visual-form .check:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color))}
.visual-form .check:has(input:checked){border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color));background:color-mix(in srgb,var(--primary-color) 4%,var(--card-background-color))}
.visual-form .check span b{font-size:13px;font-weight:500}
.visual-form .check span,.visual-form .check small{display:block}.visual-form .check small{font-weight:400;margin-top:3px;font-size:10.5px}
.visual-form .check input{appearance:none;-webkit-appearance:none;flex:0 0 auto;width:44px;height:25px;margin:0;padding:0;border:0;border-radius:99px;background:var(--divider-color);position:relative;cursor:pointer;transition:background .2s}
.visual-form .check input::after{content:'';position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0004;transition:left .2s,width .12s}
.visual-form .check input:active::after{width:23px}
.visual-form .check input:checked{background:var(--primary-color)}
.visual-form .check input:checked::after{left:22px}
.visual-form .check input:checked:active::after{left:18px}
.visual-form .check input:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.hidden-field{display:none!important}
.yaml-editor ha-alert{display:block;margin-bottom:12px}
.yaml-editor textarea{box-sizing:border-box;width:100%;height:400px;padding:16px;border-radius:14px;border:1px solid var(--divider-color);background:var(--code-editor-background-color,var(--secondary-background-color));color:var(--code-editor-text-color,var(--primary-text-color));font:13.5px/1.55 ui-monospace,'SF Mono',Consolas,monospace;resize:vertical}
.configuration-editor>ha-alert{display:block;margin-bottom:14px}.configuration-editor textarea{box-sizing:border-box;width:100%;height:min(62vh,680px);padding:16px;border-radius:14px;border:1px solid var(--divider-color);background:var(--code-editor-background-color,var(--secondary-background-color));color:var(--code-editor-text-color,var(--primary-text-color));font:13.5px/1.55 ui-monospace,'SF Mono',Consolas,monospace;resize:vertical}.configuration-tools{display:flex;justify-content:flex-end;gap:8px;margin-bottom:10px}.configuration-tools button{display:flex;align-items:center;gap:6px;padding:9px 13px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color)}
.yaml-editor textarea:focus{outline:0;border-color:var(--primary-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--primary-color) 14%,transparent)}
.editor-error{margin-top:16px}
.connection-details>p{color:var(--secondary-text-color);font-size:12.5px;font-weight:400;margin:12px 0 14px}
.connection-head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:6px 0 16px;border-bottom:1px solid var(--divider-color)}
.connection-head-text{min-width:0;display:flex;flex-direction:column;gap:3px}
.connection-head-text b{font-size:15px;letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.connection-head-text code{font-family:ui-monospace,'SF Mono',Consolas,monospace;font-size:12.5px;color:var(--secondary-text-color);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.connection-status{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;padding:4px 12px;border-radius:99px;font-size:11px;font-weight:700;letter-spacing:.03em;background:color-mix(in srgb,var(--error-color) 10%,transparent);color:var(--error-color)}
.connection-status::before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor}
.connection-status.connected{background:color-mix(in srgb,#00a86b 12%,transparent);color:var(--success-color,#008755)}
.connection-status.unknown{background:var(--secondary-background-color);color:var(--secondary-text-color)}
.availability{margin:0 0 14px;padding:13px 14px;border:1px solid var(--divider-color);border-radius:14px;background:color-mix(in srgb,var(--secondary-background-color) 28%,transparent)}
.availability-title{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:10px}.availability-title b{font-size:13px}.availability-title small,.timeline-labels,.availability-note{color:var(--secondary-text-color);font-size:10.5px}
.connection-timeline{display:flex;width:100%;height:14px;overflow:hidden;border-radius:5px;background:var(--divider-color)}.timeline-segment{display:block;min-width:1px}.timeline-segment.connected{background:var(--success-color,#00a86b)}.timeline-segment.disconnected{background:var(--error-color,#db4437)}.timeline-segment.unknown{background:#8c939b}.timeline-segment:focus-visible{outline:2px solid var(--primary-color);outline-offset:-2px}
.timeline-labels{display:flex;justify-content:space-between;margin-top:3px}.availability-stats{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));border:0!important;border-radius:0!important;overflow:visible!important;margin:10px 0 7px!important;gap:6px}.availability-stats>div{display:block!important;padding:7px 8px!important;border:0!important;border-radius:8px;background:var(--card-background-color)!important}.availability-stats dt{white-space:normal!important;font-size:10px!important}.availability-stats dd{text-align:left!important;margin-top:3px!important;font-size:12px!important}
.availability-stats-live{grid-template-columns:minmax(0,180px);margin:0 0 8px!important}
.last-disconnection{display:flex;justify-content:space-between;gap:10px!important;margin:5px 0!important;font-size:11px!important}.last-disconnection span{color:var(--secondary-text-color);text-align:right}.availability-note{display:block;margin-top:6px}.history-loading,.history-unavailable{display:flex;align-items:center;gap:8px;margin:0 0 14px!important;padding:12px;border-radius:10px;background:var(--secondary-background-color);color:var(--secondary-text-color);font-size:12px!important}.history-loading span{width:12px;height:12px;border:2px solid var(--divider-color);border-top-color:var(--primary-color);border-radius:50%;animation:s7spin .8s linear infinite}@keyframes s7spin{to{transform:rotate(360deg)}}
.connection-detail-groups{display:flex;flex-direction:column;gap:14px}.connection-detail-group h3{display:flex;align-items:center;gap:7px;margin:0 0 7px;font-size:12px;color:var(--secondary-text-color);font-weight:600}.connection-detail-group h3 ha-icon{--mdc-icon-size:16px;color:var(--primary-color)}
.connection-details .connection-detail-group dl{margin:0;border:1px solid var(--divider-color);border-radius:14px;overflow:hidden}
.connection-detail{display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding:11px 16px}
.connection-detail+.connection-detail{border-top:1px solid var(--divider-color)}
.connection-detail:nth-child(odd){background:color-mix(in srgb,var(--secondary-background-color) 35%,transparent)}
.connection-detail dt{color:var(--secondary-text-color);font-size:12.5px;font-weight:400;white-space:nowrap}
.connection-detail dd{margin:0;font-size:13px;font-family:inherit;font-weight:500;text-align:right;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.connection-detail dd.technical-value{font-family:ui-monospace,'SF Mono',Consolas,monospace}
@media(prefers-reduced-motion:reduce){.dialog-body *,.dialog-body *::before,.dialog-body *::after{transition:none!important;animation:none!important}}
@media(max-width:650px){.dialog-body{max-height:66vh;padding:0 14px 16px}.editor-intro p{display:none}.form-section{padding:14px 12px}.field-grid{grid-template-columns:1fr}.control-options{grid-template-columns:1fr}.control-card{min-height:0;flex-direction:row!important}.mode-tabs button{font-size:12px}.mode-tabs button small{display:none}.availability-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.connection-detail{gap:10px;padding:10px 12px}.connection-detail dt{white-space:normal}}`;}
}
customElements.define("s7plc-configuration-panel",S7PlcConfigurationPanel);
