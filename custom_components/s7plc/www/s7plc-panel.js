const TYPES = ["sensors", "binary_sensors", "switches", "covers", "lights", "buttons", "numbers", "texts", "climates", "entity_sync"];
const LABELS = { sensors:"Sensori", binary_sensors:"Sensori binari", switches:"Interruttori", covers:"Tapparelle", lights:"Luci", buttons:"Pulsanti", numbers:"Numeri", texts:"Testi", climates:"Clima", entity_sync:"Sincronizzazioni" };
const COMMON = [
  ["name","Nome"], ["area","Area"], ["scan_interval","Intervallo di scansione (s)","number"]
];
const FIELDS = {
  sensors:[["address","Indirizzo PLC","text",true],["device_class","Classe dispositivo"],["unit_of_measurement","Unità di misura"],["value_multiplier","Moltiplicatore","number"],["min_value","Valore minimo","number"],["max_value","Valore massimo","number"],["scale_raw_min","Scala grezza minima","number"],["scale_raw_max","Scala grezza massima","number"],["state_class","Classe di stato"],["real_precision","Decimali","number"],...COMMON],
  binary_sensors:[["address","Indirizzo PLC","text",true],["device_class","Classe dispositivo"],["invert_state","Inverti stato","checkbox"],...COMMON],
  switches:[["state_address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["sync_state","Sincronizza stato","checkbox"],["pulse_command","Comando a impulso","checkbox"],["pulse_duration","Durata impulso (s)","number"],...COMMON],
  covers:[["cover_mode","Tipo tapparella","select",true,{traditional:"Tradizionale",position:"Posizione"}],["open_command_address","Indirizzo apertura"],["close_command_address","Indirizzo chiusura"],["opening_state_address","Stato apertura"],["closing_state_address","Stato chiusura"],["position_state_address","Indirizzo posizione"],["position_command_address","Comando posizione"],["stop_command_address","Comando stop"],["stop_pulse_duration","Durata impulso stop (s)","number"],["operate_time","Tempo corsa (s)","number"],["use_state_topics","Usa indirizzi di stato","checkbox"],["invert_position","Inverti posizione","checkbox"],["device_class","Classe dispositivo"],...COMMON],
  lights:[["state_address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["sync_state","Sincronizza stato","checkbox"],["pulse_command","Comando a impulso","checkbox"],["pulse_duration","Durata impulso (s)","number"],["brightness_state_address","Stato luminosità"],["brightness_command_address","Comando luminosità"],["brightness_scale","Scala luminosità","number"],...COMMON],
  buttons:[["address","Indirizzo PLC","text",true],["button_pulse","Durata impulso (s)","number"],...COMMON.filter(x=>x[0]!=="scan_interval")],
  numbers:[["address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["device_class","Classe dispositivo"],["unit_of_measurement","Unità di misura"],["min_value","Valore minimo","number"],["max_value","Valore massimo","number"],["step","Incremento","number"],["value_multiplier","Moltiplicatore","number"],["scale_raw_min","Scala grezza minima","number"],["scale_raw_max","Scala grezza massima","number"],["real_precision","Decimali","number"],...COMMON],
  texts:[["address","Indirizzo stato","text",true],["command_address","Indirizzo comando"],["pattern","Espressione regolare"],...COMMON],
  climates:[["control_mode","Modalità controllo","select",true,{direct:"Uscite dirette",setpoint:"Setpoint"}],["current_temperature_address","Temperatura attuale","text",true],["target_temperature_address","Temperatura obiettivo"],["heating_output_address","Uscita riscaldamento"],["cooling_output_address","Uscita raffrescamento"],["heating_action_address","Stato riscaldamento"],["cooling_action_address","Stato raffrescamento"],["preset_mode_address","Modalità preset"],["hvac_status_address","Stato HVAC"],["min_temp","Temperatura minima","number"],["max_temp","Temperatura massima","number"],["temp_step","Incremento temperatura","number"],...COMMON],
  entity_sync:[["source_entity","Entità Home Assistant","text",true],["address","Indirizzo PLC","text",true],...COMMON.filter(x=>x[0]!=="scan_interval")]
};
// Campi da nascondere/rimuovere in base alla modalità selezionata (usato sia dall'editor che dal salvataggio)
const MODE_HIDDEN = {
  covers: {
    position:    ["open_command_address","close_command_address","opening_state_address","closing_state_address","operate_time","use_state_topics"],
    traditional: ["position_state_address","position_command_address","stop_command_address","stop_pulse_duration","invert_position"]
  },
  climates: {
    setpoint: ["heating_output_address","cooling_output_address","heating_action_address","cooling_action_address"],
    direct:   ["target_temperature_address","preset_mode_address","hvac_status_address"]
  }
};

class S7PlcConfigurationPanel extends HTMLElement {
  set hass(value) { this._hass = value; if (!this._loaded) this.load(); }
  set panel(value) { this._panel = value; }
  async load() {
    if (!this._hass) return; this._loaded = true;
    this.innerHTML = `<style>${this.styles}</style><div class="loading">Caricamento configurazione…</div>`;
    try { this.entries = await this._hass.callWS({type:"s7plc/config/list"}); this.entryId ||= this.entries[0]?.entry_id; this.render(); }
    catch (err) { this.innerHTML = `<ha-alert alert-type="error">${this.escape(err.message || err)}</ha-alert>`; }
  }
  render() {
    const entry=this.entries.find(e=>e.entry_id===this.entryId);
    if(!entry){this.innerHTML=`<style>${this.styles}</style><div class="empty"><ha-icon icon="mdi:memory-off"></ha-icon><h2>Nessun PLC configurato</h2><p>Aggiungi prima l'integrazione Siemens S7 da Dispositivi e servizi.</p></div>`;return;}
    const count=TYPES.reduce((n,t)=>n+entry.entities[t].length,0), type=this.type||TYPES[0];
    this.innerHTML=`<style>${this.styles}</style><div class="page"><header><div><h1>Configurazione S7 PLC</h1><p>Configura graficamente le entità o usa YAML nelle opzioni avanzate.</p></div><select id="entry">${this.entries.map(e=>`<option value="${this.escape(e.entry_id)}" ${e.entry_id===this.entryId?'selected':''}>${this.escape(e.title)}</option>`).join('')}</select></header><div class="summary"><ha-icon icon="mdi:memory"></ha-icon><div><b>${this.escape(entry.title)}</b><span>${this.escape(entry.data.host||'')} · ${count} entità</span></div></div><nav>${TYPES.map(t=>`<button data-type="${t}" class="${t===type?'active':''}"><ha-icon icon="mdi:${this.icon(t)}"></ha-icon>${LABELS[t]} <span>${entry.entities[t].length}</span></button>`).join('')}</nav><main><div class="toolbar"><div><h2>${LABELS[type]}</h2><p>Le modifiche vengono applicate ricaricando automaticamente l'integrazione.</p></div><button class="primary" id="add"><ha-icon icon="mdi:plus"></ha-icon> Aggiungi</button></div><div class="cards">${this.entityCards(entry)}</div></main></div>`;
    this.querySelector('#entry').onchange=e=>{this.entryId=e.target.value;this.render();}; this.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{this.type=b.dataset.type;this.render();}); this.querySelector('#add').onclick=()=>this.openEditor(); this.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>this.openEditor(Number(b.dataset.edit))); this.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>this.remove(Number(b.dataset.delete)));
  }
  entityCards(entry){const type=this.type||TYPES[0],items=entry.entities[type];if(!items.length)return `<div class="empty small"><ha-icon icon="mdi:playlist-plus"></ha-icon><h3>Nessuna entità</h3><p>Usa “Aggiungi” per creare la prima.</p></div>`;return items.map((item,i)=>`<article><div class="entity-icon"><ha-icon icon="mdi:${this.icon(type)}"></ha-icon></div><div class="details"><b>${this.escape(item.name||item.address||item.state_address||item.current_temperature_address||`Entità ${i+1}`)}</b><code>${this.escape(item.address||item.state_address||item.current_temperature_address||item.source_entity||'—')}</code><div>${Object.entries(item).filter(([k])=>k!=='name').slice(0,5).map(([k,v])=>`<span>${this.escape(k)}: ${this.escape(String(v))}</span>`).join('')}</div></div><button data-edit="${i}" class="icon-btn" title="Modifica"><ha-icon icon="mdi:pencil"></ha-icon></button><button data-delete="${i}" class="icon-btn danger" title="Elimina"><ha-icon icon="mdi:delete"></ha-icon></button></article>`).join('');}
  inferred(item,type){const copy={...item};if(type==='covers')copy.cover_mode=item.position_state_address?'position':'traditional';if(type==='climates')copy.control_mode=item.control_mode||(item.target_temperature_address?'setpoint':'direct');return copy;}
  field([key,label,kind='text',required=false,choices],item){const value=item[key]??'',address=key.includes('address')||key==='source_entity',placeholder=address?'es. DB1,REAL0':key==='name'?'es. Temperatura soggiorno':'';if(kind==='checkbox')return `<label class="check" data-field="${key}"><span><b>${label}</b><small>Attiva questa opzione</small></span><input name="${key}" type="checkbox" ${value?'checked':''}></label>`;const caption=`<span class="field-label">${label}${required?'<em>Obbligatorio</em>':''}</span>`;if(kind==='select')return `<label data-field="${key}">${caption}<select name="${key}" ${required?'required':''}>${Object.entries(choices).map(([v,l])=>`<option value="${v}" ${v===value?'selected':''}>${l}</option>`).join('')}</select></label>`;return `<label data-field="${key}">${caption}<input name="${key}" type="${kind}" class="${address?'mono':''}" value="${this.escape(value)}" placeholder="${placeholder}" ${kind==='number'?'step="any"':''} ${required?'required':''}>${address&&key!=='source_entity'?'<small>Formato Siemens S7, ad esempio DB1,REAL0</small>':''}</label>`;}
  editorSections(type,item){const fields=FIELDS[type],isAddress=f=>f[0].includes('address')||f[0]==='source_entity'||f[0]==='cover_mode'||f[0]==='control_mode',isIdentity=f=>['name','area','scan_interval'].includes(f[0]),section=(icon,title,description,list)=>list.length?`<section class="form-section"><div class="section-head"><span class="section-icon"><ha-icon icon="mdi:${icon}"></ha-icon></span><div><b>${title}</b><small>${description}</small></div></div><div class="field-grid">${list.map(f=>this.field(f,item)).join('')}</div></section>`:'';return section('connection','Collegamento PLC','Indirizzi e sorgenti dei dati',fields.filter(isAddress))+section('tune-variant','Comportamento','Opzioni specifiche di questa entità',fields.filter(f=>!isAddress(f)&&!isIdentity(f)))+section('card-account-details-outline','Dettagli in Home Assistant','Nome, area e frequenza di aggiornamento',fields.filter(isIdentity));}
  openEditor(index=null){const entry=this.entries.find(e=>e.entry_id===this.entryId),type=this.type||TYPES[0],raw=index===null?{}:entry.entities[type][index],initial=this.inferred(raw,type),dialog=document.createElement('ha-dialog');dialog.open=true;dialog.headerTitle=`${index===null?'Nuova entità':'Modifica entità'}`;dialog.style.setProperty('--mdc-dialog-max-width','min(940px,95vw)');dialog.style.setProperty('--mdc-dialog-min-width','min(940px,95vw)');dialog.style.setProperty('--dialog-content-padding','0');dialog.innerHTML=`<style>${this.dialogStyles}</style><div class="dialog-body"><div class="editor-intro"><span class="editor-type-icon"><ha-icon icon="mdi:${this.icon(type)}"></ha-icon></span><div><span class="eyebrow">${LABELS[type]}</span><h3>${index===null?'Configura una nuova entità':'Aggiorna la configurazione'}</h3><p>I campi vengono salvati direttamente nella configurazione del PLC.</p></div></div><div class="mode-tabs" role="tablist" aria-label="Modalità editor"><button class="active" data-mode="visual" role="tab"><ha-icon icon="mdi:form-select"></ha-icon><span>Editor grafico<small>Guidato e semplice</small></span></button><button data-mode="yaml" role="tab"><ha-icon icon="mdi:code-braces"></ha-icon><span>YAML<small>Controllo avanzato</small></span></button></div><form class="visual-form">${this.editorSections(type,initial)}</form><div class="yaml-editor" hidden><ha-alert alert-type="warning">La modalità avanzata consente di modificare manualmente tutti i campi. Usa una mappa YAML per una singola entità.</ha-alert><textarea spellcheck="false" aria-label="Configurazione YAML">${this.escape(this.toYaml(raw))}</textarea></div><ha-alert class="editor-error" alert-type="error" style="display:none"></ha-alert></div><ha-dialog-footer slot="footer"><ha-button slot="secondaryAction" appearance="plain">Annulla</ha-button><ha-button slot="primaryAction" appearance="accent">Salva modifiche</ha-button></ha-dialog-footer>`;document.body.appendChild(dialog);
    const form=dialog.querySelector('form');
    // Mostra solo i campi pertinenti alla modalità scelta (tapparelle/clima)
    const syncMode=()=>{const sel=form.elements.cover_mode||form.elements.control_mode;if(!sel)return;const hidden=MODE_HIDDEN[type]?.[sel.value]||[];form.querySelectorAll('[data-field]').forEach(l=>l.classList.toggle('hidden-field',hidden.includes(l.dataset.field)));};
    syncMode();['cover_mode','control_mode'].forEach(k=>{if(form.elements[k])form.elements[k].onchange=syncMode;});
    let mode='visual';dialog.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;dialog.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));dialog.querySelector('.visual-form').hidden=mode!=='visual';dialog.querySelector('.yaml-editor').hidden=mode!=='yaml';});dialog.querySelector('[slot=secondaryAction]').onclick=()=>{dialog.open=false;};dialog.addEventListener('closed',()=>dialog.remove());dialog.querySelector('[slot=primaryAction]').onclick=async()=>{const alert=dialog.querySelector('.editor-error');try{const msg={type:"s7plc/config/save_entity",entry_id:this.entryId,entity_type:type,index};if(mode==='yaml')msg.entity_yaml=dialog.querySelector('textarea').value;else msg.entity=this.formEntity(form,raw,type);await this._hass.callWS(msg);dialog.open=false;this._loaded=false;await this.load();}catch(err){alert.textContent=err.message||err;alert.style.display='block';alert.scrollIntoView({behavior:'smooth',block:'nearest'});}};
  }

  formEntity(form,original,type){if(!form.reportValidity())throw Error("Compila tutti i campi obbligatori.");const entity={...original};for(const field of FIELDS[type]){const [key,,,required]=field,input=form.elements[key];let value=input.type==='checkbox'?input.checked:input.value.trim();if(key==='cover_mode'||key==='control_mode')continue;if(input.type==='number'&&value!=='')value=Number(value);if(value===''&&!required)delete entity[key];else entity[key]=value;}const mode=form.elements.cover_mode?.value;if(type==='covers'){MODE_HIDDEN.covers[mode].forEach(k=>delete entity[k]);const needed=mode==='position'?'position_state_address':'open_command_address';if(!entity[needed]||(mode==='traditional'&&!entity.close_command_address))throw Error("Inserisci gli indirizzi obbligatori per il tipo di tapparella scelto.");}if(type==='climates'){entity.control_mode=form.elements.control_mode.value;MODE_HIDDEN.climates[entity.control_mode].forEach(k=>delete entity[k]);if(entity.control_mode==='setpoint'&&!entity.target_temperature_address)throw Error("Inserisci l'indirizzo della temperatura obiettivo.");}return entity;}
  toYaml(obj){return Object.entries(obj).map(([k,v])=>`${k}: ${JSON.stringify(v)}`).join('\n');}
  async remove(index){if(!confirm("Eliminare questa entità? L'azione non può essere annullata."))return;await this._hass.callWS({type:"s7plc/config/delete_entity",entry_id:this.entryId,entity_type:this.type||TYPES[0],index});this._loaded=false;await this.load();}
  icon(t){return({sensors:'gauge',binary_sensors:'checkbox-marked-circle',switches:'toggle-switch',covers:'window-shutter',lights:'lightbulb',buttons:'gesture-tap-button',numbers:'numeric',texts:'form-textbox',climates:'thermostat',entity_sync:'sync'})[t];} escape(v){const d=document.createElement('div');d.textContent=v??'';return d.innerHTML;}
  get styles(){return `
:host{display:block;background:var(--primary-background-color);min-height:100vh;color:var(--primary-text-color);font-family:Roboto,sans-serif}
.page{max-width:1180px;margin:auto;padding:32px 24px}
header,.toolbar,.summary,article{display:flex;align-items:center}
header{justify-content:space-between}
h1{font-size:30px;margin:0 0 6px}h2,p{margin:0}
header p,.toolbar p{color:var(--secondary-text-color)}
select,input{box-sizing:border-box;padding:11px 12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:inherit;font:inherit;font-size:14px}
.summary{margin:26px 0 18px;padding:18px 22px;background:linear-gradient(120deg,var(--primary-color),var(--accent-color));color:white;border-radius:16px;gap:15px;box-shadow:0 5px 18px #0002}
.summary ha-icon{--mdc-icon-size:34px}.summary div{display:flex;flex-direction:column;gap:4px}.summary span{opacity:.85}
nav{display:flex;gap:8px;overflow:auto;padding:4px 0 18px;scrollbar-width:thin}
button,.primary{border:0;border-radius:9px;padding:10px 13px;cursor:pointer;color:inherit;background:var(--card-background-color);font:inherit;font-size:13px}
nav button{white-space:nowrap;border:1px solid var(--divider-color);border-radius:99px;display:flex;align-items:center;gap:7px;padding:8px 15px;transition:border-color .15s,background .15s}
nav button ha-icon{--mdc-icon-size:17px;opacity:.75}
nav button:hover{border-color:var(--primary-color)}
nav button.active{background:var(--primary-color);color:white;border-color:var(--primary-color)}
nav button.active ha-icon{opacity:1}
nav span{opacity:.65;margin-left:2px;font-variant-numeric:tabular-nums}
.toolbar{justify-content:space-between;margin:10px 0 16px}.toolbar p{font-size:13px;margin-top:5px}
.primary{background:var(--primary-color);color:white;display:flex;align-items:center;gap:6px;box-shadow:0 2px 8px color-mix(in srgb,var(--primary-color) 35%,transparent);transition:transform .15s,box-shadow .15s}
.primary:hover{transform:translateY(-1px);box-shadow:0 4px 14px color-mix(in srgb,var(--primary-color) 45%,transparent)}
article{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:13px;margin:9px 0;padding:14px;gap:12px;transition:border-color .15s,box-shadow .15s,transform .15s}
article:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color));box-shadow:0 4px 16px #0000000f;transform:translateY(-1px)}
.entity-icon{padding:11px;border-radius:10px;background:color-mix(in srgb,var(--primary-color) 14%,transparent);color:var(--primary-color)}
.details{flex:1;min-width:0}.details>b,.details>code{display:block}
.details code{margin:4px 0 8px;color:var(--secondary-text-color);font-size:12px}
.details span{font-size:11px;background:var(--secondary-background-color);padding:4px 7px;border-radius:5px;margin:2px 4px 2px 0;display:inline-block}
.icon-btn{padding:9px;border-radius:9px;display:grid;place-items:center;background:transparent;transition:background .15s}
.icon-btn:hover{background:var(--secondary-background-color)}
.icon-btn ha-icon{--mdc-icon-size:19px}
.danger{color:var(--error-color)!important}
.danger:hover{background:color-mix(in srgb,var(--error-color) 10%,transparent)!important}
.empty{text-align:center;padding:20vh 20px}
.empty.small{padding:70px 20px;border:1px dashed var(--divider-color);border-radius:14px}
.empty ha-icon{--mdc-icon-size:55px;color:var(--secondary-text-color)}
.loading{padding:30px}
@media(prefers-reduced-motion:reduce){.page *{transition:none!important}}
@media(max-width:650px){.page{padding:20px 12px}header{align-items:flex-start;gap:14px;flex-direction:column}header select{width:100%}.details div,.toolbar p{display:none}}`;}
  get dialogStyles(){return `
.dialog-body{box-sizing:border-box;width:100%;max-height:min(76vh,860px);overflow:auto;padding:0 28px 28px;font-family:Roboto,sans-serif;color:var(--primary-text-color)}
.dialog-body h3,.dialog-body p{margin:0}
.dialog-body select,.dialog-body input:not([type=checkbox]){box-sizing:border-box;padding:11px 12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:inherit;font:inherit;font-size:14px}
.dialog-body button{border:0;cursor:pointer;color:inherit;font:inherit;font-size:13px;background:transparent}
.editor-intro{display:flex;align-items:center;gap:16px;padding:4px 2px 20px}
.editor-type-icon,.section-icon{display:grid;place-items:center;flex:0 0 auto;border-radius:12px;background:color-mix(in srgb,var(--primary-color) 14%,transparent);color:var(--primary-color)}
.editor-type-icon{width:52px;height:52px}.editor-type-icon ha-icon{--mdc-icon-size:28px}
.editor-intro h3{font-size:18px;margin:2px 0 4px}
.editor-intro p,.editor-intro .eyebrow,.section-head small,.visual-form label small{color:var(--secondary-text-color)}
.eyebrow{text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:.08em;color:var(--primary-color)!important}
.mode-tabs{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:24px;padding:5px;border-radius:13px;background:var(--secondary-background-color)}
.mode-tabs button{display:flex;text-align:left;align-items:center;justify-content:center;gap:9px;border:0;background:transparent;padding:10px;border-radius:9px;transition:background .15s,box-shadow .15s;opacity:.75}
.mode-tabs button.active{background:var(--card-background-color);box-shadow:0 1px 5px #00000022;opacity:1}
.mode-tabs button.active ha-icon{color:var(--primary-color)}
.mode-tabs button span,.mode-tabs button small{display:block}
.mode-tabs button small{font-size:10px;opacity:.72;margin-top:2px}
.visual-form{display:flex;flex-direction:column;gap:16px}
.form-section{border:1px solid var(--divider-color);border-radius:16px;padding:20px 22px;background:color-mix(in srgb,var(--secondary-background-color) 40%,transparent)}
.section-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.section-head b{display:block;font-size:14px}
.section-head small{display:block;font-size:11px;margin-top:2px}
.section-icon{width:34px;height:34px}.section-icon ha-icon{--mdc-icon-size:19px}
.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 18px}
.visual-form label:not(.check){display:flex;flex-direction:column;gap:8px;font-size:13px}
.visual-form input,.visual-form select{width:100%;background:var(--card-background-color);transition:border-color .15s,box-shadow .15s}
.visual-form input:hover,.visual-form select:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color))}
.visual-form input:focus,.visual-form select:focus{outline:0;border-color:var(--primary-color);box-shadow:0 0 0 3px color-mix(in srgb,var(--primary-color) 18%,transparent)}
.visual-form input.mono{font-family:ui-monospace,'SF Mono',Consolas,monospace;font-size:13px;letter-spacing:.02em}
.field-label{display:flex;align-items:center;justify-content:space-between;font-weight:500}
.field-label em{font-size:9px;font-style:normal;text-transform:uppercase;letter-spacing:.05em;color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 12%,transparent);border-radius:10px;padding:3px 7px}
.visual-form label small{font-size:10.5px}
.visual-form .check{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px;padding:8px 14px;border-radius:11px;background:var(--card-background-color);border:1px solid var(--divider-color);cursor:pointer;transition:border-color .15s}
.visual-form .check:hover{border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color))}
.visual-form .check span b{font-size:13px;font-weight:500}
.visual-form .check span,.visual-form .check small{display:block}.visual-form .check small{font-weight:400;margin-top:3px;font-size:10.5px}
.visual-form .check input{appearance:none;-webkit-appearance:none;flex:0 0 auto;width:42px;height:24px;margin:0;padding:0;border:0;border-radius:99px;background:var(--divider-color);position:relative;cursor:pointer;transition:background .2s}
.visual-form .check input::after{content:'';position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0004;transition:left .2s}
.visual-form .check input:checked{background:var(--primary-color)}
.visual-form .check input:checked::after{left:21px}
.visual-form .check input:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.hidden-field{display:none!important}
.yaml-editor ha-alert{display:block;margin-bottom:12px}
.yaml-editor textarea{box-sizing:border-box;width:100%;height:400px;padding:16px;border-radius:10px;border:1px solid var(--divider-color);background:var(--code-editor-background-color,#1e1e1e);color:var(--code-editor-text-color,#eee);font:13.5px/1.55 ui-monospace,'SF Mono',Consolas,monospace;resize:vertical}
.yaml-editor textarea:focus{outline:0;border-color:var(--primary-color)}
.editor-error{margin-top:16px}
@media(prefers-reduced-motion:reduce){.dialog-body *{transition:none!important}}
@media(max-width:650px){.dialog-body{max-height:66vh;padding:0 14px 16px}.editor-intro p{display:none}.form-section{padding:14px 12px}.field-grid{grid-template-columns:1fr}.mode-tabs button{font-size:12px}.mode-tabs button small{display:none}}`;}
}
customElements.define("s7plc-configuration-panel",S7PlcConfigurationPanel);
