const TYPES = ["sensors", "binary_sensors", "switches", "covers", "lights", "buttons", "numbers", "texts", "climates", "entity_sync"];
const LABELS = { sensors:"Sensori", binary_sensors:"Sensori binari", switches:"Interruttori", covers:"Tapparelle", lights:"Luci", buttons:"Pulsanti", numbers:"Numeri", texts:"Testi", climates:"Clima", entity_sync:"Sincronizzazioni" };

class S7PlcConfigurationPanel extends HTMLElement {
  set hass(value) { this._hass = value; if (!this._loaded) this.load(); }
  set panel(value) { this._panel = value; }

  async load() {
    if (!this._hass) return;
    this._loaded = true;
    this.innerHTML = `<style>${this.styles}</style><div class="loading">Caricamento configurazione…</div>`;
    try { this.entries = await this._hass.callWS({type:"s7plc/config/list"}); this.entryId = this.entryId || this.entries[0]?.entry_id; this.render(); }
    catch (err) { this.innerHTML = `<ha-alert alert-type="error">${this.escape(err.message || err)}</ha-alert>`; }
  }

  render() {
    const entry = this.entries.find(e => e.entry_id === this.entryId);
    if (!entry) { this.innerHTML = `<style>${this.styles}</style><div class="empty"><ha-icon icon="mdi:memory-off"></ha-icon><h2>Nessun PLC configurato</h2><p>Aggiungi prima l'integrazione Siemens S7 da Dispositivi e servizi.</p></div>`; return; }
    const count = TYPES.reduce((n,t) => n + entry.entities[t].length, 0);
    this.innerHTML = `<style>${this.styles}</style><div class="page">
      <header><div><h1>Configurazione S7 PLC</h1><p>Gestisci tutte le entità senza passare dall'option flow.</p></div>
      <select id="entry">${this.entries.map(e=>`<option value="${this.escape(e.entry_id)}" ${e.entry_id===this.entryId?'selected':''}>${this.escape(e.title)}</option>`).join('')}</select></header>
      <div class="summary"><ha-icon icon="mdi:memory"></ha-icon><div><b>${this.escape(entry.title)}</b><span>${this.escape(entry.data.host || '')} · ${count} entità</span></div></div>
      <nav>${TYPES.map(t=>`<button data-type="${t}" class="${t===(this.type||TYPES[0])?'active':''}">${LABELS[t]} <span>${entry.entities[t].length}</span></button>`).join('')}</nav>
      <main><div class="toolbar"><div><h2>${LABELS[this.type||TYPES[0]]}</h2><p>Le modifiche vengono applicate ricaricando automaticamente l'integrazione.</p></div><button class="primary" id="add"><ha-icon icon="mdi:plus"></ha-icon> Aggiungi</button></div>
      <div class="cards">${this.entityCards(entry)}</div></main></div>`;
    this.querySelector('#entry').onchange = e => { this.entryId=e.target.value; this.render(); };
    this.querySelectorAll('nav button').forEach(b => b.onclick=()=>{this.type=b.dataset.type;this.render();});
    this.querySelector('#add').onclick=()=>this.openEditor();
    this.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>this.openEditor(Number(b.dataset.edit)));
    this.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>this.remove(Number(b.dataset.delete)));
  }

  entityCards(entry) {
    const type=this.type||TYPES[0], items=entry.entities[type];
    if (!items.length) return `<div class="empty small"><ha-icon icon="mdi:playlist-plus"></ha-icon><h3>Nessuna entità</h3><p>Usa “Aggiungi” per creare la prima.</p></div>`;
    return items.map((item,i)=>`<article><div class="entity-icon"><ha-icon icon="mdi:${this.icon(type)}"></ha-icon></div><div class="details"><b>${this.escape(item.name || item.address || item.state_address || `Entità ${i+1}`)}</b><code>${this.escape(item.address || item.state_address || item.current_temperature_address || item.source_entity || '—')}</code><div>${Object.entries(item).slice(0,5).map(([k,v])=>`<span>${this.escape(k)}: ${this.escape(String(v))}</span>`).join('')}</div></div><button data-edit="${i}" title="Modifica"><ha-icon icon="mdi:pencil"></ha-icon></button><button data-delete="${i}" class="danger" title="Elimina"><ha-icon icon="mdi:delete"></ha-icon></button></article>`).join('');
  }

  openEditor(index=null) {
    const entry=this.entries.find(e=>e.entry_id===this.entryId), type=this.type||TYPES[0];
    const initial=index===null?{name:"",address:""}:entry.entities[type][index];
    const dialog=document.createElement('ha-dialog'); dialog.open=true; dialog.heading=`${index===null?'Aggiungi':'Modifica'} · ${LABELS[type]}`;
    dialog.innerHTML=`<div class="dialog-body"><p>Inserisci la configurazione dell'entità in formato JSON. I campi supportati sono gli stessi dell'integrazione; questo editor permette anche configurazioni avanzate.</p><textarea>${this.escape(JSON.stringify(initial,null,2))}</textarea><ha-alert alert-type="error" style="display:none"></ha-alert></div><ha-button slot="secondaryAction">Annulla</ha-button><ha-button slot="primaryAction">Salva</ha-button>`;
    document.body.appendChild(dialog); dialog.querySelector('[slot=secondaryAction]').onclick=()=>dialog.close();
    dialog.addEventListener('closed',()=>dialog.remove());
    dialog.querySelector('[slot=primaryAction]').onclick=async()=>{ const alert=dialog.querySelector('ha-alert'); try { const entity=JSON.parse(dialog.querySelector('textarea').value); if(!entity||Array.isArray(entity)||typeof entity!=="object") throw Error("La configurazione deve essere un oggetto JSON."); await this._hass.callWS({type:"s7plc/config/save_entity",entry_id:this.entryId,entity_type:type,index,entity}); dialog.close(); await this.load(); } catch(err){alert.textContent=err.message||err;alert.style.display='block';} };
  }

  async remove(index) { if(!confirm("Eliminare questa entità? L'azione non può essere annullata.")) return; await this._hass.callWS({type:"s7plc/config/delete_entity",entry_id:this.entryId,entity_type:this.type||TYPES[0],index}); await this.load(); }
  icon(t){return ({sensors:'gauge',binary_sensors:'checkbox-marked-circle',switches:'toggle-switch',covers:'window-shutter',lights:'lightbulb',buttons:'gesture-tap-button',numbers:'numeric',texts:'form-textbox',climates:'thermostat',entity_sync:'sync'})[t];}
  escape(v){const d=document.createElement('div');d.textContent=v??'';return d.innerHTML;}
  get styles(){return `:host{display:block;background:var(--primary-background-color);min-height:100vh;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}.page{max-width:1180px;margin:auto;padding:32px 24px}header,.toolbar,.summary,article{display:flex;align-items:center}header{justify-content:space-between}h1{font-size:30px;margin:0 0 6px}h2,p{margin:0}header p,.toolbar p{color:var(--secondary-text-color)}select{padding:12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:inherit}.summary{margin:26px 0 18px;padding:18px 22px;background:linear-gradient(120deg,var(--primary-color),var(--accent-color));color:white;border-radius:16px;gap:15px;box-shadow:0 5px 18px #0002}.summary ha-icon{--mdc-icon-size:34px}.summary div{display:flex;flex-direction:column;gap:4px}.summary span{opacity:.85}nav{display:flex;gap:8px;overflow:auto;padding:4px 0 18px}nav button,.primary,article>button{border:0;border-radius:9px;padding:10px 13px;cursor:pointer;color:inherit;background:var(--card-background-color)}nav button{white-space:nowrap;border:1px solid var(--divider-color)}nav button.active{background:var(--primary-color);color:white;border-color:var(--primary-color)}nav span{opacity:.65;margin-left:5px}.toolbar{justify-content:space-between;margin:10px 0 16px}.toolbar p{font-size:13px;margin-top:5px}.primary{background:var(--primary-color);color:white;display:flex;align-items:center;gap:6px}article{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:13px;margin:9px 0;padding:14px;gap:12px}.entity-icon{padding:11px;border-radius:10px;background:color-mix(in srgb,var(--primary-color) 14%,transparent);color:var(--primary-color)}.details{flex:1;min-width:0}.details>b,.details>code{display:block}.details code{margin:4px 0 8px;color:var(--secondary-text-color)}.details span{font-size:11px;background:var(--secondary-background-color);padding:4px 7px;border-radius:5px;margin:2px 4px 2px 0;display:inline-block}.danger{color:var(--error-color)!important}.empty{text-align:center;padding:20vh 20px}.empty.small{padding:70px 20px;border:1px dashed var(--divider-color);border-radius:14px}.empty ha-icon{--mdc-icon-size:55px;color:var(--secondary-text-color)}.dialog-body{width:min(650px,75vw);padding:0 24px 18px}.dialog-body p{color:var(--secondary-text-color);margin-bottom:14px}.dialog-body textarea{box-sizing:border-box;width:100%;height:360px;padding:14px;border-radius:8px;border:1px solid var(--divider-color);background:var(--code-editor-background-color,#1e1e1e);color:var(--code-editor-text-color,#eee);font:14px monospace}.loading{padding:30px}@media(max-width:650px){.page{padding:20px 12px}header{align-items:flex-start;gap:14px;flex-direction:column}header select{width:100%}.details div{display:none}.toolbar p{display:none}article{gap:8px}}`;}
}
customElements.define("s7plc-configuration-panel", S7PlcConfigurationPanel);
