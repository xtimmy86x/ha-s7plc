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
      below_min: "WORD {word} is below minimum {min}.", above_max: "WORD {word} exceeds maximum {max}.",
      invalid_step: "Incompatible entity step: use step 1 for the raw WORD.",
      unconfirmed: "Value sent but not confirmed by HA. Check before retrying.",
      waiting: "Waiting for HA…", sending: "Sending…", modified: "Modified", saving: "Saving…",
      saving_status: "Sending changes to Home Assistant…", hint: "Edit hours and minutes, then save.",
      saved: "Times updated in Home Assistant.", invalid_bcd: "Invalid BCD ({raw}).",
      write_failed: "Write failed: {error}", pending_count: "{count} times awaiting confirmation from Home Assistant…",
      failed_count: "{sent} sends succeeded, {failed} failed. Check the highlighted fields.",
      invalid_count: "{count} modified times. Correct the highlighted fields.",
      dirty_count: "{count} modified times. Press Save changes to send them.",
      incompatible: "This S7 entity is not a raw writable WORD. Check datatype and conversions.",
      choose_entity: "Choose an entity", configure: "Open the card editor and add your on/off entity pairs.",
      editor_title: "Title", editor_name: "Slot name", editor_raw: "Show raw WORD values",
      editor_timeout: "Confirmation timeout (seconds)", editor_add: "Add slot", editor_remove: "Remove slot",
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
      below_min: "WORD {word} inferiore al minimo {min}.", above_max: "WORD {word} superiore al massimo {max}.",
      invalid_step: "Passo dell'entità incompatibile: usa step 1 per il WORD.",
      unconfirmed: "Valore inviato, ma non confermato da HA. Verifica prima di riprovare.",
      waiting: "In attesa di HA…", sending: "Invio…", modified: "Modificato", saving: "Salvataggio…",
      saving_status: "Invio delle modifiche a Home Assistant…", hint: "Modifica ore e minuti, poi salva.",
      saved: "Orari aggiornati in Home Assistant.", invalid_bcd: "BCD non valido ({raw}).",
      write_failed: "Scrittura fallita: {error}", pending_count: "{count} orari in attesa di conferma da Home Assistant…",
      failed_count: "{sent} invii riusciti, {failed} non riusciti. Controlla i campi segnalati.",
      invalid_count: "{count} orari modificati. Correggi i campi segnalati.",
      dirty_count: "{count} orari modificati. Premi Salva modifiche per inviarli.",
      incompatible: "Questa entità S7 non è un WORD grezzo scrivibile. Verifica tipo e conversioni.",
      choose_entity: "Scegli un'entità", configure: "Apri l'editor della card e aggiungi le coppie accensione/spegnimento.",
      editor_title: "Titolo", editor_name: "Nome fascia", editor_raw: "Mostra valori WORD grezzi",
      editor_timeout: "Tempo di conferma (secondi)", editor_add: "Aggiungi fascia", editor_remove: "Elimina fascia",
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
  const decode = (raw) => {
    const n = parseWord(raw);
    if (n === null) return null;
    const digits = [n >> 12, (n >> 8) & 15, (n >> 4) & 15, n & 15];
    if (digits.some((d) => d > 9)) return null;
    const hours = digits[0] * 10 + digits[1];
    const minutes = digits[2] * 10 + digits[3];
    if (hours > 23 || minutes > 59) return null;
    return { hours: pad(hours), minutes: pad(minutes) };
  };
  const encode = (hours, minutes) => {
    if (!/^\d{1,2}$/.test(String(hours)) || !/^\d{1,2}$/.test(String(minutes))) return null;
    const h = Number(hours), m = Number(minutes);
    if (h > 23 || m > 59) return null;
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
    static encodeTime(hours, minutes) { return encode(hours, minutes); }

    setConfig(config) {
      if (!config || !Array.isArray(config.rows)) {
        throw new Error("Configure rows with name, on_entity and off_entity.");
      }
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
      const word = parseWord(raw);
      return { state, raw, available, word, time: decode(raw), key: word ?? String(raw) };
    }

    _edit(cell) {
      if (this._saving || cell.pending) return;
      const info = this._info(cell);
      cell.draft = {
        base: cell.draft?.base ?? cell.focusBase ?? info.key,
        hours: cell.hours.value, minutes: cell.minutes.value,
      };
      cell.error = "";
      if (encode(cell.draft.hours, cell.draft.minutes) === info.word && info.word !== null) cell.draft = null;
      this._message = "";
      this._sync();
    }

    _validate(cell) {
      if (!cell.draft) return "";
      const info = this._info(cell);
      if (info.state?.attributes?.s7_raw_word === false) return this._t("incompatible");
      if (!info.available) return this._t("unavailable");
      const word = encode(cell.draft.hours, cell.draft.minutes);
      if (word === null) return this._t("invalid_time");
      if (info.key !== cell.draft.base && info.word !== word) {
        return this._t("conflict");
      }
      const attrs = info.state.attributes ?? {};
      if (attrs.min != null && word < Number(attrs.min)) return this._t("below_min", {word, min: attrs.min});
      if (attrs.max != null && word > Number(attrs.max)) return this._t("above_max", {word, max: attrs.max});
      const step = Number(attrs.step);
      if (Number.isFinite(step) && step > 0) {
        const steps = (word - Number(attrs.min ?? 0)) / step;
        if (Math.abs(steps - Math.round(steps)) > 1e-6) return this._t("invalid_step");
      }
      return "";
    }

    _sync() {
      if (!this._config || !this._status) return;
      let dirty = 0, pending = 0, invalid = 0;
      for (const c of this._cells) {
        const info = this._info(c);
        if (c.pending?.accepted && info.available && info.word === c.pending.word) {
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
        c.hours.disabled = c.minutes.disabled = !info.available || info.state?.attributes?.s7_raw_word === false || this._saving || Boolean(c.pending);
        let problem = c.pending ? "" : (c.error || this._validate(c));
        if (info.state?.attributes?.s7_raw_word === false) problem = this._t("incompatible");
        else if (!info.available) problem = !c.entity ? this._t("choose_entity") : info.state ? this._t("unavailable") : this._t("missing");
        else if (!c.draft && !info.time) problem = this._t("invalid_bcd", {raw: String(info.raw)});
        c.note.textContent = problem || (c.pending ? (c.pending.accepted ? this._t("waiting") : this._t("sending")) : c.draft ? this._t("modified") : "");
        c.td.toggleAttribute("data-error", Boolean(problem));
        c.td.toggleAttribute("data-dirty", Boolean(c.draft));
        c.hours.setAttribute("aria-invalid", String(Boolean(problem)));
        c.minutes.setAttribute("aria-invalid", String(Boolean(problem)));
        c.raw.textContent = this._config.show_raw && info.available ? `WORD ${String(info.raw)}` : "";
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
        const word = encode(cell.draft.hours, cell.draft.minutes);
        if (this._info(cell).word === word) { cell.draft = null; cell.error = ""; continue; }
        cell.error = "";
        cell.pending = { word, accepted: false };
        this._sync();
        try {
          await this._hass.callService(cell.entity.split(".")[0], "set_value", {
            entity_id: cell.entity, value: word,
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
    }

    _t(key) { return translate(this._hass, key); }

    setConfig(config) {
      // HA echoes config-changed. Keep the focused field alive on that echo.
      const next = {...config, rows: (config.rows ?? []).map(row => ({...row}))};
      if (this.shadowRoot.childNodes.length && JSON.stringify(next) === JSON.stringify(this._config)) return;
      this._config = next;
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      const options = this._options();
      const signature = JSON.stringify([language(hass), options]);
      if (signature !== this._signature) {
        // Do not rebuild while editing a name/title as HA states update.
        if (!this.shadowRoot.activeElement) this._render();
      }
    }

    _options() {
      return Object.entries(this._hass?.states ?? {})
        .filter(([id, state]) => /^(number|input_number)\./.test(id) && state.attributes?.s7_raw_word !== false)
        .map(([id, state]) => [id, state.attributes?.friendly_name || id])
        .sort((a, b) => a[1].localeCompare(b[1]) || a[0].localeCompare(b[0]));
    }

    _emit(render = false) {
      this._config = {...this._config, type: "custom:s7plc-schedule-card"};
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: {config: {...this._config, rows: this._config.rows.map(row => ({...row}))}},
        bubbles: true, composed: true,
      }));
      if (render) this._render();
    }

    _render() {
      this._signature = JSON.stringify([language(this._hass), this._options()]);
      this.shadowRoot.replaceChildren();
      const style = el("style");
      style.textContent = `
        :host { display:block; color:var(--primary-text-color); font-family:inherit; }
        * { box-sizing:border-box; }
        .hint { font-size:13px; line-height:1.5; color:var(--secondary-text-color); }
        label { display:block; font-size:13px; margin:10px 0; }
        input:not([type=checkbox]),select { display:block; width:100%; min-width:0; min-height:40px; margin-top:5px;
          padding:8px; border:1px solid var(--divider-color,#aaa); border-radius:6px; font:inherit;
          color:var(--primary-text-color,#222); background:var(--card-background-color,#fff); }
        fieldset { min-width:0; border:1px solid var(--divider-color,#aaa); border-radius:8px; margin:16px 0; padding:12px; }
        legend { font-weight:600; font-size:14px; }
        button { min-height:36px; padding:6px 12px; border:1px solid var(--divider-color,#aaa); border-radius:6px;
          background:var(--card-background-color,#fff); color:var(--primary-color,#0288d1); font:inherit; cursor:pointer; }
        button:disabled { opacity:.4; cursor:default; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
      `;
      this.shadowRoot.append(style, el("p", "hint", this._t("editor_hint")));
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
      const options = this._options();
      this._config.rows.forEach((row, index) => {
        const group = el("fieldset");
        group.append(el("legend", "", `${this._t("row")} ${index + 1}`));
        const name = field(group, this._t("editor_name"), el("input"));
        name.value = row.name ?? "";
        name.addEventListener("input", () => {row.name = name.value; this._emit();});
        for (const [key, caption] of [["on_entity", "on"], ["off_entity", "off"]]) {
          const select = field(group, this._t(caption), el("select"));
          const blank = el("option", "", this._t("editor_choose")); blank.value = ""; select.append(blank);
          for (const [id, label] of options) {
            const option = el("option", "", `${label} (${id})`); option.value = id; select.append(option);
          }
          if (row[key] && !options.some(([id]) => id === row[key])) {
            const option = el("option", "", `${row[key]} — ${this._t("editor_unavailable")}`);
            option.value = row[key]; select.append(option);
          }
          select.value = row[key] ?? "";
          select.addEventListener("change", () => {row[key] = select.value; this._emit();});
        }
        const actions = el("div", "actions");
        for (const [key, delta] of [["editor_up", -1], ["editor_down", 1], ["editor_remove", 0]]) {
          const button = el("button", "", this._t(key)); button.type = "button";
          button.setAttribute("aria-label", `${this._t(key)} ${index + 1}`);
          button.disabled = delta !== 0 && (index + delta < 0 || index + delta >= this._config.rows.length);
          button.addEventListener("click", () => {
            if (!delta) this._config.rows.splice(index, 1);
            else [this._config.rows[index], this._config.rows[index + delta]] =
              [this._config.rows[index + delta], this._config.rows[index]];
            this._emit(true);
          });
          actions.append(button);
        }
        group.append(actions); this.shadowRoot.append(group);
      });
      const add = el("button", "", this._t("editor_add")); add.type = "button";
      add.addEventListener("click", () => {
        this._config.rows.push({name: "", on_entity: "", off_entity: ""}); this._emit(true);
      });
      this.shadowRoot.append(add);
    }
  }

  if (!customElements.get("s7plc-schedule-card-editor")) customElements.define("s7plc-schedule-card-editor", S7ScheduleCardEditor);
  if (!customElements.get("s7plc-schedule-card")) customElements.define("s7plc-schedule-card", S7ScheduleCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "s7plc-schedule-card")) {
    window.customCards.push({ type: "s7plc-schedule-card", name: "S7 PLC — Schedule",
      description: "Editable on/off schedule stored in raw BCD WORD entities.", preview: false,
      documentationURL: "https://github.com/xtimmy86x/ha-s7plc/blob/main/docs/schedule-card.md" });
  }
})();
