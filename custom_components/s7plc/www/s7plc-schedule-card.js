/* S7 PLC Schedule Card — bundled dashboard card and visual editor. */
(() => {
  "use strict";

  const messages = {
    en: {
      title: "Time schedule", row: "Slot", on: "On time", off: "Off time", hours: "hours", minutes: "minutes",
      subtitle: "{count} slots · 24-hour format", save: "Save changes", cancel: "Cancel",
      cancelled: "Local changes discarded.", unavailable: "Unavailable", missing: "Entity not found",
      invalid_time: "Enter hours 00–23 and minutes 00–59.",
      conflict: "Value changed in HA. Cancel and read it again before editing.",
      below_min: "Value {value} is below minimum {min}.", above_max: "Value {value} exceeds maximum {max}.",
      invalid_step: "Incompatible entity step: use step 1 for clock values.",
      unconfirmed: "Value sent but not confirmed by HA. Check before retrying.",
      waiting: "Waiting for HA…", sending: "Sending…", modified: "Modified", saving: "Saving…",
      saving_status: "Sending changes to Home Assistant…", hint: "Edit hours and minutes, then save.",
      saved: "Times updated in Home Assistant.", invalid_bcd: "Invalid BCD ({raw}).", invalid_hhmm: "Invalid HHMM ({raw}).",
      write_failed: "Write failed: {error}", pending_count: "{count} times awaiting confirmation from Home Assistant…",
      failed_count: "{sent} sends succeeded, {failed} failed. Check the highlighted fields.",
      invalid_count: "{count} modified times. Correct the highlighted fields.",
      dirty_count: "{count} modified times. Press Save changes to send them.",
      incompatible: "This S7 entity is incompatible with the selected value format. Check datatype and conversions.",
      choose_entity: "Choose an entity", configure: "Open the card editor and add your on/off entity pairs.",
      editor_title: "Title", editor_name: "Slot name", editor_raw: "Show entity values",
      editor_timeout: "Confirmation timeout (seconds)", editor_add: "Add slot", editor_remove: "Remove slot",
      editor_format: "Entity value format", editor_bcd: "Raw BCD WORD (1024 = 04:00)",
      editor_hhmm: "Converted HHMM (400 = 04:00)",
      editor_hint_hhmm: "Select numbers using the LOGO! time BCD conversion, or HHMM helpers. HA writes HHMM; the integration packs the PLC WORD.",
      editor_search: "Search by name or entity ID", editor_no_results: "No matching entities",
      editor_plc: "Filter by PLC", editor_all_plcs: "All entities",
      editor_expand: "Expand all", editor_collapse: "Collapse all",
      editor_incomplete: "Select both entities", editor_in_use: "Already assigned to another time",
      editor_up: "Move up", editor_down: "Move down", editor_choose: "Select a number entity…",
      editor_hint: "Select raw WORD entities with step 1 and no conversion. The PLC executes the schedule.",
      editor_unavailable: "Unavailable or incompatible", editor_timeout_error: "Enter a timeout from 1 to 300 seconds.",
    },
    it: {
      title: "Programmazione oraria", row: "Fascia", on: "Accensione", off: "Spegnimento", hours: "ore", minutes: "minuti",
      subtitle: "{count} fasce · Orari in formato 24 ore", save: "Salva modifiche", cancel: "Annulla",
      cancelled: "Modifiche locali annullate.", unavailable: "Non disponibile", missing: "Entità non trovata",
      invalid_time: "Inserisci ore 00–23 e minuti 00–59.",
      conflict: "Valore cambiato in HA. Annulla e rileggi prima di modificare.",
      below_min: "Valore {value} inferiore al minimo {min}.", above_max: "Valore {value} superiore al massimo {max}.",
      invalid_step: "Passo dell'entità incompatibile: usa step 1 per gli orari.",
      unconfirmed: "Valore inviato, ma non confermato da HA. Verifica prima di riprovare.",
      waiting: "In attesa di HA…", sending: "Invio…", modified: "Modificato", saving: "Salvataggio…",
      saving_status: "Invio delle modifiche a Home Assistant…", hint: "Modifica ore e minuti, poi salva.",
      saved: "Orari aggiornati in Home Assistant.", invalid_bcd: "BCD non valido ({raw}).", invalid_hhmm: "HHMM non valido ({raw}).",
      write_failed: "Scrittura fallita: {error}", pending_count: "{count} orari in attesa di conferma da Home Assistant…",
      failed_count: "{sent} invii riusciti, {failed} non riusciti. Controlla i campi segnalati.",
      invalid_count: "{count} orari modificati. Correggi i campi segnalati.",
      dirty_count: "{count} orari modificati. Premi Salva modifiche per inviarli.",
      incompatible: "Questa entità S7 non è compatibile con il formato scelto. Verifica tipo e conversioni.",
      choose_entity: "Scegli un'entità", configure: "Apri l'editor della card e aggiungi le coppie accensione/spegnimento.",
      editor_title: "Titolo", editor_name: "Nome fascia", editor_raw: "Mostra valori delle entità",
      editor_timeout: "Tempo di conferma (secondi)", editor_add: "Aggiungi fascia", editor_remove: "Elimina fascia",
      editor_format: "Formato valori delle entità", editor_bcd: "WORD BCD grezzo (1024 = 04:00)",
      editor_hhmm: "HHMM convertito (400 = 04:00)",
      editor_hint_hhmm: "Seleziona number con conversione LOGO! time BCD o helper HHMM. HA invia HHMM; l’integrazione converte nel WORD del PLC.",
      editor_search: "Cerca per nome o ID entità", editor_no_results: "Nessuna entità trovata",
      editor_plc: "Filtra per PLC", editor_all_plcs: "Tutte le entità",
      editor_expand: "Espandi tutte", editor_collapse: "Chiudi tutte",
      editor_incomplete: "Seleziona entrambe le entità", editor_in_use: "Già assegnata a un altro orario",
      editor_up: "Sposta su", editor_down: "Sposta giù", editor_choose: "Seleziona un'entità number…",
      editor_hint: "Seleziona entità WORD grezze con passo 1 e senza conversioni. La programmazione è eseguita dal PLC.",
      editor_unavailable: "Non disponibile o incompatibile", editor_timeout_error: "Inserisci un tempo tra 1 e 300 secondi.",
    },
  };
  const language = (hass) => String(hass?.locale?.language || hass?.language || "en").split(/[-_]/)[0];
  const translate = (hass, key, values = {}) => (messages[language(hass)]?.[key] ?? messages.en[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`));

  const pad = (n) => String(n).padStart(2, "0");
  const parseWord = (raw) => {
    if (typeof raw !== "number" && typeof raw !== "string") return null;
    const text = String(raw).trim();
    if (!/^\d+(?:\.0+)?$/.test(text)) return null;
    const n = Number(text);
    return Number.isInteger(n) && n >= 0 && n <= 65535 ? n : null;
  };
  const valueFormat = config => config?.time_format ?? "bcd";
  const compatible = (state, format) => {
    const attrs = state?.attributes ?? {};
    if (attrs.s7_time_format != null) return attrs.s7_time_format === format;
    if (attrs.s7_raw_word === true) return format === "bcd";
    return attrs.s7_raw_word !== false;
  };
  const decode = (raw, format = "bcd") => {
    const n = parseWord(raw);
    if (n === null) return null;
    if (format === "hhmm") {
      const hours = Math.floor(n / 100), minutes = n % 100;
      return hours <= 23 && minutes <= 59 ? {hours: pad(hours), minutes: pad(minutes)} : null;
    }
    const digits = [n >> 12, (n >> 8) & 15, (n >> 4) & 15, n & 15];
    if (digits.some((d) => d > 9)) return null;
    const hours = digits[0] * 10 + digits[1];
    const minutes = digits[2] * 10 + digits[3];
    if (hours > 23 || minutes > 59) return null;
    return { hours: pad(hours), minutes: pad(minutes) };
  };
  const encode = (hours, minutes, format = "bcd") => {
    if (!/^\d{1,2}$/.test(String(hours)) || !/^\d{1,2}$/.test(String(minutes))) return null;
    const h = Number(hours), m = Number(minutes);
    if (h > 23 || m > 59) return null;
    if (format === "hhmm") return h * 100 + m;
    return (Math.floor(h / 10) << 12) | ((h % 10) << 8) |
      (Math.floor(m / 10) << 4) | (m % 10);
  };
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  class S7ScheduleCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._cells = [];
      this._generation = 0;
      this._saving = false;
      this._message = "";
    }

    // These pure helpers also make the encoding independently testable.
    static decodeWord(raw) { return decode(raw); }
    static encodeTime(hours, minutes, format = "bcd") { return encode(hours, minutes, format); }
    static decodeHHMM(raw) { return decode(raw, "hhmm"); }

    setConfig(config) {
      if (!config || !Array.isArray(config.rows)) {
        throw new Error("Configure rows with name, on_entity and off_entity.");
      }
      if (!["bcd", "hhmm"].includes(valueFormat(config))) throw new Error("time_format must be bcd or hhmm.");
      const seen = new Set();
      const rows = config.rows.map((row, i) => {
        if (!row || typeof row !== "object") throw new Error(`Invalid row ${i + 1}.`);
        for (const key of ["on_entity", "off_entity"]) {
          if (row[key] != null && row[key] !== "" && (typeof row[key] !== "string" || !/^(number|input_number)\.[a-z0-9_]+$/.test(row[key]))) {
            throw new Error(`Row ${i + 1}: ${key} must be a number or input_number entity.`);
          }
          if (row[key] && seen.has(row[key])) throw new Error(`Duplicate entity: ${row[key]}`);
          seen.add(row[key]);
        }
        return { ...row, name: String(row.name ?? ""), index: i };
      });
      const timeout = Number(config.confirmation_timeout ?? 15);
      if (!Number.isFinite(timeout) || timeout < 1 || timeout > 300) {
        throw new Error("confirmation_timeout must be between 1 and 300 seconds.");
      }
      this._config = { ...config, rows, confirmation_timeout: timeout };
      this._generation++;
      this._saving = false;
      this._message = "";
      this._build();
      this._sync();
    }

    set hass(hass) {
      this._hass = hass;
      // Rebuild labels only when idle; never replace fields or in-flight cell
      // objects while the user is editing or a service request is outstanding.
      if (language(hass) !== this._renderLanguage && this._config && !this._saving &&
          !this._cells.some(c => c.draft || c.pending) && !this.shadowRoot.activeElement) {
        this._build();
      }
      this._sync();
    }
    _t(key, values) { return translate(this._hass, key, values); }
    static getConfigElement() { return document.createElement("s7plc-schedule-card-editor"); }
    static getStubConfig() { return { rows: [] }; }
    get hass() { return this._hass; }
    getCardSize() { return Math.ceil(((this._config?.rows.length ?? 12) * 66 + 170) / 50); }
    getGridOptions() { return { columns: 12, min_columns: 9 }; }
    connectedCallback() {
      if (!this._timer) this._timer = setInterval(() => {
        if (this._cells.some((c) => c.pending)) this._sync();
      }, 1000);
      this._sync();
    }
    disconnectedCallback() { clearInterval(this._timer); this._timer = null; }

    _build() {
      this._renderLanguage = language(this._hass);
      this.shadowRoot.replaceChildren();
      const style = el("style");
      style.textContent = `
        :host { display:block; color:var(--primary-text-color,#182a36);
          font-family:var(--paper-font-body1_-_font-family,Roboto,Arial,sans-serif); }
        * { box-sizing:border-box; }
        ha-card { display:block; overflow:hidden; background:var(--ha-card-background,var(--card-background-color,#fff));
          border:var(--ha-card-border-width,1px) solid var(--ha-card-border-color,var(--divider-color,#dce3e8));
          border-radius:var(--ha-card-border-radius,16px); box-shadow:var(--ha-card-box-shadow,none); }
        header { padding:22px 20px 18px; }
        h2 { font-size:20px; font-weight:600; line-height:1.4; margin:0 0 6px; }
        .subtitle { font-size:13px; color:var(--secondary-text-color,#647887); }
        .scroll { overflow-x:auto; }
        table { border-collapse:collapse; table-layout:fixed; width:100%; min-width:288px; }
        th, td { padding:10px 8px; border-bottom:1px solid var(--divider-color,#e7edf0); }
        thead th { padding-top:12px; padding-bottom:12px; font-size:12px; font-weight:600;
          background:var(--secondary-background-color,#f4f7f9); color:var(--secondary-text-color,#647887); }
        thead th:first-child { width:29%; text-align:left; padding-left:20px; }
        tbody th { text-align:left; font-size:13px; font-weight:500; padding-left:20px; overflow-wrap:anywhere; }
        td { text-align:center; vertical-align:top; }
        tr:last-child th, tr:last-child td { border-bottom:0; }
        .time { display:inline-flex; align-items:center; justify-content:center; gap:3px; }
        input { width:35px; height:38px; min-width:0; padding:0 2px; text-align:center; font-weight:500;
          font-family:inherit; font-size:16px; font-variant-numeric:tabular-nums; border-radius:6px;
          border:1px solid var(--divider-color,#d7e0e6); background:var(--input-fill-color,var(--card-background-color,#fff));
          color:var(--primary-text-color,#182a36); outline:none; }
        input:focus { border-color:var(--primary-color,#0288d1); box-shadow:0 0 0 1px var(--primary-color,#0288d1); }
        input:disabled { opacity:.55; cursor:not-allowed; }
        .colon { color:var(--secondary-text-color,#647887); }
        td[data-dirty] input { border-color:var(--primary-color,#0288d1); }
        td[data-error] input { border-color:var(--error-color,#c33b39); }
        .note { display:block; font-size:11px; line-height:1.35; margin-top:5px; overflow-wrap:anywhere;
          color:var(--secondary-text-color,#647887); }
        .note:empty, .raw:empty { display:none; }
        td[data-error] .note { color:var(--error-color,#c33b39); }
        .raw { display:block; font-size:10px; margin-top:4px; color:var(--secondary-text-color,#647887); }
        footer { padding:15px 20px 18px; border-top:1px solid var(--divider-color,#e7edf0); }
        .status { font-size:12px; line-height:1.5; min-height:18px; color:var(--secondary-text-color,#647887); }
        .buttons { display:flex; justify-content:flex-end; gap:8px; margin-top:12px; flex-wrap:wrap; }
        button { min-height:40px; padding:8px 14px; border-radius:8px; border:0; font-weight:500;
          font-family:inherit; font-size:14px; cursor:pointer; }
        button:focus-visible { outline:2px solid var(--primary-color,#0288d1); outline-offset:2px; }
        .save { background:var(--primary-color,#0288d1); color:var(--text-primary-color,#fff); }
        .reset { background:transparent; color:var(--primary-color,#0288d1); }
        button:disabled { opacity:.45; cursor:default; }
        @media (max-width:380px) { header { padding:18px 12px 14px; }
          thead th:first-child, tbody th { padding-left:12px; } th,td { padding-left:4px; padding-right:4px; }
          footer { padding-left:12px; padding-right:12px; } }
      `;
      const card = el("ha-card");
      const header = el("header");
      header.append(el("h2", "", (this._config.title ?? this._t("title"))),
        el("div", "subtitle", this._t("subtitle", {count: this._config.rows.length})));
      const scroll = el("div", "scroll");
      const table = el("table");
      table.setAttribute("aria-label", (this._config.title ?? this._t("title")));
      const head = el("thead"), headings = el("tr");
      for (const label of [this._t("row"), this._t("on"), this._t("off")]) {
        const th = el("th", "", label); th.scope = "col"; headings.append(th);
      }
      head.append(headings);
      const body = el("tbody");
      this._cells = [];
      for (const row of this._config.rows) {
        const tr = el("tr"), label = el("th", "", (row.name || `${this._t("row")} ${pad(row.index + 1)}`));
        label.scope = "row";
        tr.append(label);
        for (const [key, caption] of [["on_entity", this._t("on")], ["off_entity", this._t("off")]]) {
          const td = el("td"), group = el("div", "time");
          const hours = el("input"), minutes = el("input");
          const note = el("span", "note"), raw = el("span", "raw");
          const cell = { entity: row[key], td, hours, minutes, note, raw, draft: null, pending: null, error: "" };
          for (const [input, part, max] of [[hours, this._t("hours"), 23], [minutes, this._t("minutes"), 59]]) {
            input.type = "text";
            input.inputMode = "numeric";
            input.maxLength = 2;
            input.pattern = "[0-9]{1,2}";
            input.placeholder = "--";
            input.autocomplete = "off";
            input.setAttribute("aria-label", `${(row.name || `${this._t("row")} ${pad(row.index + 1)}`)} — ${caption}: ${part}`);
            input.title = `${row[key]} · ${part} 00–${max}`;
            input.addEventListener("focus", (event) => {
              if (!cell.draft && ![hours, minutes].includes(event.relatedTarget)) cell.focusBase = this._info(cell).key;
            });
            input.addEventListener("input", () => this._edit(cell));
            input.addEventListener("blur", () => {
              if (/^\d{1,2}$/.test(input.value)) input.value = pad(input.value);
              if (cell.draft) {
                cell.draft.hours = hours.value; cell.draft.minutes = minutes.value;
              }
              queueMicrotask(() => this._sync());
            });
          }
          group.append(hours, el("span", "colon", ":"), minutes);
          td.append(group, raw, note);
          tr.append(td);
          this._cells.push(cell);
        }
        body.append(tr);
      }
      table.append(head, body); scroll.append(table);
      const footer = el("footer");
      this._status = el("div", "status");
      this._status.setAttribute("role", "status");
      this._status.setAttribute("aria-live", "polite");
      const buttons = el("div", "buttons");
      this._reset = el("button", "reset", this._t("cancel"));
      this._save = el("button", "save", this._t("save"));
      this._reset.type = this._save.type = "button";
      this._reset.addEventListener("click", () => {
        if (this._saving || this._cells.some((c) => c.pending)) return;
        for (const c of this._cells) { c.draft = null; c.error = ""; }
        this._message = this._t("cancelled");
        this._sync();
      });
      this._save.addEventListener("click", () => void this._saveChanges());
      buttons.append(this._reset, this._save); footer.append(this._status, buttons);
      card.append(header, scroll, footer); this.shadowRoot.append(style, card);
    }

    _info(cell) {
      const state = this._hass?.states?.[cell.entity];
      const raw = state?.state;
      const available = Boolean(state) && raw !== "unknown" && raw !== "unavailable";
      const value = parseWord(raw);
      const format = valueFormat(this._config), isCompatible = compatible(state, format);
      return { state, raw, available, value, compatible: isCompatible,
        time: isCompatible ? decode(raw, format) : null, key: value ?? String(raw) };
    }

    _edit(cell) {
      if (this._saving || cell.pending) return;
      const info = this._info(cell);
      cell.draft = {
        base: cell.draft?.base ?? cell.focusBase ?? info.key,
        hours: cell.hours.value, minutes: cell.minutes.value,
      };
      cell.error = "";
      if (encode(cell.draft.hours, cell.draft.minutes, valueFormat(this._config)) === info.value && info.value !== null) cell.draft = null;
      this._message = "";
      this._sync();
    }

    _validate(cell) {
      if (!cell.draft) return "";
      const info = this._info(cell);
      if (!info.compatible) return this._t("incompatible");
      if (!info.available) return this._t("unavailable");
      const value = encode(cell.draft.hours, cell.draft.minutes, valueFormat(this._config));
      if (value === null) return this._t("invalid_time");
      if (info.key !== cell.draft.base && info.value !== value) {
        return this._t("conflict");
      }
      const attrs = info.state.attributes ?? {};
      if (attrs.min != null && value < Number(attrs.min)) return this._t("below_min", {value, min: attrs.min});
      if (attrs.max != null && value > Number(attrs.max)) return this._t("above_max", {value, max: attrs.max});
      const step = Number(attrs.step);
      if (Number.isFinite(step) && step > 0) {
        const steps = (value - Number(attrs.min ?? 0)) / step;
        if (Math.abs(steps - Math.round(steps)) > 1e-6) return this._t("invalid_step");
      }
      return "";
    }

    _sync() {
      if (!this._config || !this._status) return;
      let dirty = 0, pending = 0, invalid = 0;
      for (const c of this._cells) {
        const info = this._info(c);
        if (c.pending?.accepted && info.available && info.compatible && info.value === c.pending.value) {
          c.pending = null; c.draft = null; c.error = "";
        } else if (c.pending?.accepted && Date.now() > c.pending.deadline) {
          c.pending = null;
          c.error = this._t("unconfirmed");
        }
        const focused = [c.hours, c.minutes].includes(this.shadowRoot.activeElement);
        if (!focused) {
          const value = c.draft ?? info.time;
          c.hours.value = value?.hours ?? ""; c.minutes.value = value?.minutes ?? "";
        }
        c.hours.disabled = c.minutes.disabled = !info.available || !info.compatible || this._saving || Boolean(c.pending);
        let problem = c.pending ? "" : (c.error || this._validate(c));
        if (!info.compatible) problem = this._t("incompatible");
        else if (!info.available) problem = !c.entity ? this._t("choose_entity") : info.state ? this._t("unavailable") : this._t("missing");
        else if (!c.draft && !info.time) problem = this._t(valueFormat(this._config) === "hhmm" ? "invalid_hhmm" : "invalid_bcd", {raw: String(info.raw)});
        c.note.textContent = problem || (c.pending ? (c.pending.accepted ? this._t("waiting") : this._t("sending")) : c.draft ? this._t("modified") : "");
        c.td.toggleAttribute("data-error", Boolean(problem));
        c.td.toggleAttribute("data-dirty", Boolean(c.draft));
        c.hours.setAttribute("aria-invalid", String(Boolean(problem)));
        c.minutes.setAttribute("aria-invalid", String(Boolean(problem)));
        c.raw.textContent = this._config.show_raw && info.available ? `${valueFormat(this._config) === "hhmm" ? "HHMM" : "WORD"} ${String(info.raw)}` : "";
        if (c.draft && !c.pending) { dirty++; if (this._validate(c)) invalid++; }
        if (c.pending) pending++;
      }
      this._save.disabled = !this._hass || this._saving || pending > 0 || dirty === 0 || invalid > 0;
      this._reset.disabled = this._saving || pending > 0 || dirty === 0;
      this._save.textContent = this._saving ? this._t("saving") : this._t("save");
      this._status.textContent = this._saving ? this._t("saving_status") :
        pending ? this._t("pending_count", {count: pending}) :
        dirty ? this._t(invalid ? "invalid_count" : "dirty_count", {count: dirty}) :
        this._message || this._t(this._config.rows.length ? "hint" : "configure");
    }

    async _saveChanges() {
      if (this._saving || !this._hass || this._cells.some((c) => c.pending)) return;
      const changes = this._cells.filter((c) => c.draft);
      if (!changes.length) return;
      if (changes.some((c) => this._validate(c))) { this._sync(); return; }
      const generation = this._generation;
      this._saving = true;
      this._message = "";
      this._sync();
      let sent = 0, failed = 0;
      for (const cell of changes) {
        if (generation !== this._generation) return;
        // Recheck after each await: availability and values can change mid-save.
        const problem = this._validate(cell);
        if (problem) { cell.error = problem; failed++; continue; }
        const value = encode(cell.draft.hours, cell.draft.minutes, valueFormat(this._config));
        if (this._info(cell).value === value) { cell.draft = null; cell.error = ""; continue; }
        cell.error = "";
        cell.pending = { value, accepted: false };
        this._sync();
        try {
          await this._hass.callService(cell.entity.split(".")[0], "set_value", {
            entity_id: cell.entity, value,
          });
          if (generation !== this._generation) return;
          cell.pending.accepted = true;
          cell.pending.deadline = Date.now() + this._config.confirmation_timeout * 1000;
          sent++;
        } catch (error) {
          if (generation !== this._generation) return;
          cell.pending = null;
          cell.error = this._t("write_failed", {error: error?.message || String(error)});
          failed++;
        }
        this._sync();
      }
      this._saving = false;
      this._message = failed ? this._t("failed_count", {sent, failed}) :
        this._t("saved");
      this._sync();
    }
  }

  class S7ScheduleCardEditor extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: "open"});
      this._config = {type: "custom:s7plc-schedule-card", rows: []};
      this._rowUI = [];
      this._plc = "";
      this._groups = [];
      this.shadowRoot.addEventListener("focusout", () => queueMicrotask(() => {
        if (this.isConnected && !this.shadowRoot.activeElement && this._needsRender()) this._render();
      }));
    }

    _t(key) { return translate(this._hass, key); }

    connectedCallback() {
      if (this._needsRender()) this._render(); else this._refresh();
      // Load the built-in entities editor through HA's public card helpers.
      // Its imports register ha-entity-picker even on a fresh dashboard session.
      this._loadPicker();
    }

    async _loadPicker() {
      if (customElements.get("ha-entity-picker") || this._loadingPicker || !window.loadCardHelpers) return;
      this._loadingPicker = true;
      try {
        const helpers = await window.loadCardHelpers();
        const card = helpers.createCardElement({type: "entities", entities: []});
        await card.constructor.getConfigElement();
        if (this.isConnected && !this.shadowRoot.activeElement && this._needsRender()) this._render();
      } catch {
        // The searchable HTML controls remain usable if HA helpers cannot load.
      } finally {
        this._loadingPicker = false;
      }
    }

    _needsRender() {
      return this._renderLanguage !== language(this._hass) ||
        this._nativePicker !== Boolean(customElements.get("ha-entity-picker"));
    }

    setConfig(config) {
      const next = {...config, rows: (config.rows ?? []).map(row => ({...row}))};
      // HA echoes config-changed. Keep open sections, picker search and focus.
      if (this.shadowRoot.childNodes.length && JSON.stringify(next) === JSON.stringify(this._config)) return;
      const remaining = this._config.rows.map((row, i) => ({row, ui: this._rowUI[i]}));
      this._rowUI = next.rows.map((row, index) => {
        const match = remaining.findIndex(old => old.row.on_entity === row.on_entity && old.row.off_entity === row.off_entity);
        return (match >= 0 ? remaining.splice(match, 1)[0].ui : null) ?? {open: index === 0, queries: {}};
      });
      this._config = next;
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this.shadowRoot.activeElement && this._needsRender()) this._render();
      else this._refresh();
    }

    _options() {
      return Object.entries(this._hass?.states ?? {})
        .filter(([id, state]) => /^(number|input_number)\./.test(id) && compatible(state, valueFormat(this._config)))
        .map(([id, state]) => [id, state.attributes?.friendly_name || id])
        .sort((a, b) => a[1].localeCompare(b[1]) || a[0].localeCompare(b[0]));
    }

    _deviceId(id) { return this._hass?.entities?.[id]?.device_id ?? ""; }

    _choices(row, key, options) {
      const used = new Set();
      for (const other of this._config.rows) for (const field of ["on_entity", "off_entity"]) {
        if (other !== row || field !== key) used.add(other[field]);
      }
      return options.filter(([id]) => !used.has(id) && (!this._plc || this._deviceId(id) === this._plc));
    }

    _emit(render = false) {
      this._config = {...this._config, type: "custom:s7plc-schedule-card"};
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: {config: {...this._config, rows: this._config.rows.map(row => ({...row}))}},
        bubbles: true, composed: true,
      }));
      if (render) this._render(); else this._refresh();
    }

    _select(row, key, value) {
      const next = value ?? "";
      if (typeof next !== "string" || next === (row[key] ?? "")) return;
      if (next && !this._choices(row, key, this._options()).some(([id]) => id === next)) { this._refresh(); return; }
      row[key] = next;
      this._emit();
    }

    _refresh() {
      if (!this._plcSelect) return;
      const options = this._options();
      this._formatHint.textContent = this._t(valueFormat(this._config) === "hhmm" ? "editor_hint_hhmm" : "editor_hint");
      const devices = new Map();
      for (const [id] of options) {
        const attrs = this._hass.states[id].attributes;
        if (attrs?.s7_raw_word !== true && attrs?.s7_time_format !== "hhmm") continue;
        const deviceId = this._deviceId(id), device = this._hass?.devices?.[deviceId];
        if (device) devices.set(deviceId, device.name_by_user || device.name || deviceId);
      }
      // Keep a temporarily missing filter visible until the user clears it.
      if (this._plc && !devices.has(this._plc)) devices.set(this._plc, this._plc);
      const deviceOptions = [["", this._t("editor_all_plcs")], ...[...devices].sort((a, b) => a[1].localeCompare(b[1]))];
      const deviceSignature = JSON.stringify(deviceOptions);
      if (this._deviceSignature !== deviceSignature) {
        this._deviceSignature = deviceSignature;
        this._plcSelect.replaceChildren(...deviceOptions.map(([id, name]) => {
          const option = el("option", "", name); option.value = id; return option;
        }));
        this._plcSelect.value = this._plc;
      }
      this._plcSelect.parentElement.hidden = devices.size === 0;
      for (const group of this._groups) {
        const {row, index, title, descriptions, warning, fields} = group;
        title.textContent = `${this._t("row")} ${pad(index + 1)}${row.name ? ` — ${row.name}` : ""}`;
        warning.textContent = !row.on_entity || !row.off_entity ? this._t("editor_incomplete") : "";
        for (const {key, caption, picker, search, note} of fields) {
          const id = row[key] ?? "", state = this._hass?.states?.[id];
          const isCompatible = compatible(state, valueFormat(this._config));
          const time = isCompatible ? decode(state?.state, valueFormat(this._config)) : null;
          descriptions[key].textContent = `${this._t(caption)}: ${state?.attributes?.friendly_name || id || "—"}${time ? ` · ${time.hours}:${time.minutes}` : ""}`;
          descriptions[key].title = id;
          const duplicate = id && this._config.rows.some(other =>
            ["on_entity", "off_entity"].some(field => (other !== row || field !== key) && other[field] === id));
          const problem = id && (!state || !isCompatible) ? this._t("editor_unavailable") :
            duplicate ? this._t("editor_in_use") : "";
          note.textContent = problem;
          if (problem) warning.textContent = problem;
          const choices = this._choices(row, key, options);
          if (this._nativePicker) {
            picker.hass = this._hass;
            picker.value = id;
            const allowed = choices.map(([entity]) => entity);
            const signature = JSON.stringify(allowed);
            if (picker._choicesSignature !== signature) {
              picker._choicesSignature = signature;
              picker.includeEntities = allowed;
              const ids = new Set(allowed);
              picker.entityFilter = entity => ids.has(entity.entity_id);
            }
          } else {
            const query = search.value.trim().toLocaleLowerCase();
            const matches = choices.filter(([entity, name]) => `${name} ${entity}`.toLocaleLowerCase().includes(query));
            const signature = JSON.stringify([id, matches, problem]);
            if (picker._choicesSignature === signature) continue;
            picker._choicesSignature = signature;
            const blank = el("option", "", matches.length ? this._t("editor_choose") : this._t("editor_no_results"));
            blank.value = "";
            const items = matches.map(([entity, name]) => {
              const option = el("option", "", `${name} (${entity})`); option.value = entity; return option;
            });
            if (id && !matches.some(([entity]) => entity === id)) {
              const selected = el("option", "", `${state?.attributes?.friendly_name || id} (${id})${problem ? ` — ${problem}` : ""}`);
              selected.value = id; items.unshift(selected);
            }
            picker.replaceChildren(blank, ...items); picker.value = id;
          }
        }
      }
    }

    _render() {
      this._renderLanguage = language(this._hass);
      this._nativePicker = Boolean(customElements.get("ha-entity-picker"));
      this._deviceSignature = null;
      this._groups = [];
      this.shadowRoot.replaceChildren();
      const style = el("style");
      style.textContent = `
        :host { display:block; color:var(--primary-text-color); font-family:inherit; }
        * { box-sizing:border-box; }
        [hidden] { display:none !important; }
        .hint, .slot-entity, .warning, .picker-note { font-size:13px; line-height:1.5; color:var(--secondary-text-color); }
        label { display:block; font-size:13px; margin:10px 0; }
        input:not([type=checkbox]),select { display:block; width:100%; min-width:0; min-height:44px; margin-top:5px;
          padding:8px; border:1px solid var(--divider-color,#aaa); border-radius:6px; font:inherit;
          color:var(--primary-text-color,#222); background:var(--card-background-color,#fff); }
        details { min-width:0; border:1px solid var(--divider-color,#aaa); border-radius:8px; margin:12px 0; }
        summary { padding:12px; cursor:pointer; min-height:44px; }
        .slot-title { font-weight:600; font-size:14px; overflow-wrap:anywhere; }
        .slot-entity { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-inline-start:18px; }
        .warning { display:block; color:var(--error-color,#c33b39); }
        .warning:empty, .picker-note:empty { display:none; }
        fieldset { min-width:0; border:0; margin:0; padding:0 12px 12px; }
        legend { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
        ha-entity-picker { display:block; margin:14px 0 4px; }
        .picker-note { color:var(--error-color,#c33b39); }
        button { min-height:40px; padding:6px 12px; border:1px solid var(--divider-color,#aaa); border-radius:6px;
          background:var(--card-background-color,#fff); color:var(--primary-color,#0288d1); font:inherit; cursor:pointer; }
        button:disabled { opacity:.4; cursor:default; }
        button:focus-visible, summary:focus-visible { outline:2px solid var(--primary-color,#0288d1); outline-offset:2px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
      `;
      this._formatHint = el("p", "hint");
      this.shadowRoot.append(style, this._formatHint);
      const field = (parent, text, input) => {
        const label = el("label", "", text); label.append(input); parent.append(label); return input;
      };
      const title = field(this.shadowRoot, this._t("editor_title"), el("input"));
      title.value = this._config.title ?? "";
      title.placeholder = this._t("title");
      title.addEventListener("input", () => {
        if (title.value) this._config.title = title.value; else delete this._config.title;
        this._emit();
      });
      const format = field(this.shadowRoot, this._t("editor_format"), el("select", "time-format"));
      for (const value of ["bcd", "hhmm"]) {
        const option = el("option", "", this._t(`editor_${value}`)); option.value = value; format.append(option);
      }
      format.value = valueFormat(this._config);
      format.addEventListener("change", () => {
        this._config.time_format = format.value;
        this._emit();
      });
      const timeout = field(this.shadowRoot, this._t("editor_timeout"), el("input"));
      timeout.type = "number"; timeout.min = "1"; timeout.max = "300"; timeout.step = "1";
      timeout.value = this._config.confirmation_timeout ?? 15;
      timeout.addEventListener("input", () => {
        const n = Number(timeout.value);
        const valid = timeout.value !== "" && Number.isFinite(n) && n >= 1 && n <= 300;
        timeout.setCustomValidity(valid ? "" : this._t("editor_timeout_error"));
        if (valid) { this._config.confirmation_timeout = n; this._emit(); }
      });
      const raw = field(this.shadowRoot, this._t("editor_raw"), el("input"));
      raw.type = "checkbox"; raw.checked = Boolean(this._config.show_raw);
      raw.addEventListener("change", () => {this._config.show_raw = raw.checked; this._emit();});
      this._plcSelect = field(this.shadowRoot, this._t("editor_plc"), el("select", "plc-filter"));
      this._plcSelect.addEventListener("change", () => { this._plc = this._plcSelect.value; this._refresh(); });
      const sections = el("div", "actions");
      for (const [key, open] of [["editor_expand", true], ["editor_collapse", false]]) {
        const button = el("button", "", this._t(key)); button.type = "button";
        button.disabled = !this._config.rows.length;
        button.addEventListener("click", () => {
          this._groups.forEach((group, i) => {group.details.open = open; this._rowUI[i].open = open;});
        });
        sections.append(button);
      }
      this.shadowRoot.append(sections);
      this._config.rows.forEach((row, index) => {
        const ui = this._rowUI[index];
        const details = el("details", "slot"), summary = el("summary");
        details.open = ui.open;
        details.addEventListener("toggle", () => {ui.open = details.open;});
        const summaryTitle = el("span", "slot-title"), warning = el("span", "warning");
        const descriptions = {on_entity: el("span", "slot-entity"), off_entity: el("span", "slot-entity")};
        summary.append(summaryTitle, descriptions.on_entity, descriptions.off_entity, warning);
        const group = el("fieldset");
        group.append(el("legend", "", `${this._t("row")} ${index + 1}`));
        const name = field(group, this._t("editor_name"), el("input"));
        name.value = row.name ?? "";
        name.addEventListener("input", () => {row.name = name.value; this._emit();});
        const fields = [];
        for (const [key, caption] of [["on_entity", "on"], ["off_entity", "off"]]) {
          let picker, search;
          if (this._nativePicker) {
            picker = el("ha-entity-picker");
            picker.label = this._t(caption); picker.includeDomains = ["number", "input_number"];
            picker.allowCustomEntity = false; picker.showEntityId = true;
            picker.addEventListener("value-changed", event => {event.stopPropagation(); this._select(row, key, event.detail?.value);});
            group.append(picker);
          } else {
            search = field(group, `${this._t(caption)} — ${this._t("editor_search")}`, el("input", "entity-search"));
            search.type = "search"; search.autocomplete = "off"; search.value = ui.queries[key] ?? "";
            search.addEventListener("input", () => {ui.queries[key] = search.value; this._refresh();});
            picker = field(group, this._t(caption), el("select", "entity-select"));
            picker.addEventListener("change", () => this._select(row, key, picker.value));
          }
          const note = el("div", "picker-note"); note.setAttribute("role", "status"); group.append(note);
          fields.push({key, caption, picker, search, note});
        }
        const actions = el("div", "actions");
        for (const [key, delta] of [["editor_up", -1], ["editor_down", 1], ["editor_remove", 0]]) {
          const button = el("button", "", this._t(key)); button.type = "button";
          button.setAttribute("aria-label", `${this._t(key)} ${index + 1}`);
          button.disabled = delta !== 0 && (index + delta < 0 || index + delta >= this._config.rows.length);
          button.addEventListener("click", () => {
            // Capture native toggle state before moving the corresponding row.
            this._groups.forEach((g, i) => {this._rowUI[i].open = g.details.open;});
            const target = index + delta;
            if (!delta) {this._config.rows.splice(index, 1); this._rowUI.splice(index, 1);}
            else {
              [this._config.rows[index], this._config.rows[target]] = [this._config.rows[target], this._config.rows[index]];
              [this._rowUI[index], this._rowUI[target]] = [this._rowUI[target], this._rowUI[index]];
            }
            this._emit(true);
            const focus = this._groups[Math.min(Math.max(target, 0), this._groups.length - 1)]?.details.querySelector("summary");
            (focus ?? this._add).focus();
          });
          actions.append(button);
        }
        group.append(actions); details.append(summary, group); this.shadowRoot.append(details);
        this._groups.push({row, index, details, title: summaryTitle, descriptions, warning, fields});
      });
      this._add = el("button", "", this._t("editor_add")); this._add.type = "button";
      this._add.addEventListener("click", () => {
        this._groups.forEach((g, i) => {this._rowUI[i].open = g.details.open;});
        this._config.rows.push({name: "", on_entity: "", off_entity: ""});
        this._rowUI.push({open: true, queries: {}}); this._emit(true);
        this._groups.at(-1).details.querySelector("fieldset input").focus();
      });
      this.shadowRoot.append(this._add);
      this._refresh();
    }
  }

  if (!customElements.get("s7plc-schedule-card-editor")) customElements.define("s7plc-schedule-card-editor", S7ScheduleCardEditor);
  if (!customElements.get("s7plc-schedule-card")) customElements.define("s7plc-schedule-card", S7ScheduleCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "s7plc-schedule-card")) {
    window.customCards.push({ type: "s7plc-schedule-card", name: "S7 PLC — Schedule",
      description: "Editable on/off schedule using BCD WORD or converted HHMM entities.", preview: false,
      documentationURL: "https://github.com/xtimmy86x/ha-s7plc/blob/main/docs/schedule-card.md" });
  }
})();
