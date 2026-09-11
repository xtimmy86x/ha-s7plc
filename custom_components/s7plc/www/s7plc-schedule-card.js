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
      incompatible: "This S7 entity is not a supported clock value. Check datatype and conversions.",
      choose_entity: "Choose an entity", configure: "Open the card editor and add your on/off entity pairs.",
      editor_title: "Title", editor_name: "Slot name", editor_raw: "Show entity values",
      editor_timeout: "Confirmation timeout (seconds)", editor_add: "Add slot", editor_remove: "Remove slot",
      editor_search: "Search by name or entity ID", editor_no_results: "No matching entities",
      editor_plc: "Filter by PLC", editor_all_plcs: "All entities",
      editor_expand: "Expand all", editor_collapse: "Collapse all",
      editor_incomplete: "Select both entities", editor_in_use: "Already assigned to another time",
      editor_up: "Move up", editor_down: "Move down", editor_choose: "Select a number entity…",
      editor_hint: "Time formats are detected automatically from S7 entity attributes. The PLC executes the schedule.",
      editor_unavailable: "Unavailable or incompatible", editor_timeout_error: "Enter a timeout from 1 to 300 seconds.",
      bulk_title: "Add multiple slots", bulk_hint: "Select on and off entities, then review each pair. Initial order follows entity IDs (1, 2, …, 12); use the arrows to adjust it.",
      bulk_all: "Select results", bulk_clear: "Clear selection", bulk_preview: "Pairing preview",
      bulk_counts: "{on} on entities · {off} off entities", bulk_incomplete: "Select the same non-zero number of on and off entities.",
      bulk_invalid: "Some selected entities are missing, incompatible or already assigned. Review the highlighted pairs.",
      bulk_add: "Add {count} slots", bulk_ready: "Adds these pairs after the existing slots. Review and save the card configuration in HA.",
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
      incompatible: "Questa entità S7 non espone un orario supportato. Verifica tipo e conversioni.",
      choose_entity: "Scegli un'entità", configure: "Apri l'editor della card e aggiungi le coppie accensione/spegnimento.",
      editor_title: "Titolo", editor_name: "Nome fascia", editor_raw: "Mostra valori delle entità",
      editor_timeout: "Tempo di conferma (secondi)", editor_add: "Aggiungi fascia", editor_remove: "Elimina fascia",
      editor_search: "Cerca per nome o ID entità", editor_no_results: "Nessuna entità trovata",
      editor_plc: "Filtra per PLC", editor_all_plcs: "Tutte le entità",
      editor_expand: "Espandi tutte", editor_collapse: "Chiudi tutte",
      editor_incomplete: "Seleziona entrambe le entità", editor_in_use: "Già assegnata a un altro orario",
      editor_up: "Sposta su", editor_down: "Sposta giù", editor_choose: "Seleziona un'entità number…",
      editor_hint: "Il formato degli orari viene riconosciuto automaticamente dagli attributi delle entità S7. La programmazione è eseguita dal PLC.",
      editor_unavailable: "Non disponibile o incompatibile", editor_timeout_error: "Inserisci un tempo tra 1 e 300 secondi.",
      bulk_title: "Configurazione multipla guidata", bulk_hint: "Seleziona accensioni e spegnimenti, poi controlla ogni coppia. L’ordine iniziale segue gli ID entità (1, 2, …, 12); usa le frecce per modificarlo.",
      bulk_all: "Seleziona risultati", bulk_clear: "Svuota selezione", bulk_preview: "Anteprima abbinamenti",
      bulk_counts: "{on} accensioni · {off} spegnimenti", bulk_incomplete: "Seleziona lo stesso numero di accensioni e spegnimenti, almeno una per tipo.",
      bulk_invalid: "Alcune entità selezionate sono mancanti, incompatibili o già assegnate. Controlla le coppie evidenziate.",
      bulk_add: "Aggiungi {count} fasce", bulk_ready: "Aggiunge queste coppie dopo le fasce esistenti. Controlla e salva la configurazione della card in HA.",
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
  const legacyFormat = config => config?.time_format ?? "bcd";
  const formatKey = key => key.replace("_entity", "_format");
  const legacyFieldFormat = (config, row, key) => row?.[formatKey(key)] ?? legacyFormat(config);
  const resolveFormat = (state, legacy) => {
    const attrs = state?.attributes ?? {};
    if (attrs.s7_time_format === "hhmm") return "hhmm";
    if (attrs.s7_raw_word != null || attrs.s7_time_format != null) return "bcd";
    // Preserve existing external-helper configurations; S7 metadata always wins.
    return legacy === "hhmm" ? "hhmm" : "bcd";
  };
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
      if (!["auto", "bcd", "hhmm"].includes(legacyFormat(config))) throw new Error("time_format must be auto, bcd or hhmm.");
      const seen = new Set();
      const rows = config.rows.map((row, i) => {
        if (!row || typeof row !== "object") throw new Error(`Invalid row ${i + 1}.`);
        for (const key of ["on_entity", "off_entity"]) {
          if (!["auto", "bcd", "hhmm"].includes(legacyFieldFormat(config, row, key))) {
            throw new Error(`Row ${i + 1}: ${formatKey(key)} must be auto, bcd or hhmm.`);
          }
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
        @media (max-width:600px), (any-pointer:coarse) {
          .scroll { max-height:min(50vh,420px); max-height:min(50dvh,420px);
            overflow-y:auto; scroll-padding-block:48px 12px; }
          thead th { position:sticky; top:0; z-index:1; }
          thead th:first-child { width:24%; }
          thead th:first-child, tbody th { padding-left:12px; }
          th, td { padding-left:4px; padding-right:4px; }
          .time { gap:2px; }
          input { width:44px; height:44px; }
          header { padding:18px 12px 14px; }
          footer { padding:12px; }
          .buttons { margin-top:8px; }
          button { min-height:44px; flex:1 1 100px; }
        }
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
          const cell = { entity: row[key], legacyFormat: legacyFieldFormat(this._config, row, key), td, hours, minutes, note, raw, draft: null, pending: null, error: "" };
          for (const [input, part, max] of [[hours, this._t("hours"), 23], [minutes, this._t("minutes"), 59]]) {
            input.type = "text";
            input.inputMode = "numeric";
            input.maxLength = 2;
            input.pattern = "[0-9]{1,2}";
            input.placeholder = "--";
            input.autocomplete = "off";
            input.setAttribute("aria-label", `${(row.name || `${this._t("row")} ${pad(row.index + 1)}`)} — ${caption}: ${part}`);
            input.title = `${row[key]} · ${part} 00–${max}`;
            let selectAfterClick = false;
            input.addEventListener("pointerdown", () => {
              selectAfterClick = this.shadowRoot.activeElement !== input;
            });
            input.addEventListener("pointercancel", () => {selectAfterClick = false;});
            input.addEventListener("focus", (event) => {
              if (!cell.draft && ![hours, minutes].includes(event.relatedTarget)) {
                const info = this._info(cell);
                cell.focusBase = info.key; cell.focusFormat = info.format;
              }
              input.select();
            });
            input.addEventListener("click", () => {
              // Touch/click default handling can collapse the focus selection.
              // Reapply it on first entry only; later taps may position a caret.
              if (selectAfterClick) input.select();
              selectAfterClick = false;
            });
            input.addEventListener("input", () => this._edit(cell));
            input.addEventListener("blur", () => {
              selectAfterClick = false;
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
      const format = resolveFormat(state, cell.legacyFormat), isCompatible = compatible(state, format);
      return { state, raw, available, value, format, compatible: isCompatible,
        time: isCompatible ? decode(raw, format) : null, key: value ?? String(raw) };
    }

    _edit(cell) {
      if (this._saving || cell.pending) return;
      const info = this._info(cell);
      cell.draft = {
        base: cell.draft?.base ?? cell.focusBase ?? info.key,
        format: cell.draft?.format ?? cell.focusFormat ?? info.format,
        hours: cell.hours.value, minutes: cell.minutes.value,
      };
      cell.error = "";
      if (cell.draft.format === info.format && encode(cell.draft.hours, cell.draft.minutes, info.format) === info.value && info.value !== null) cell.draft = null;
      this._message = "";
      this._sync();
    }

    _validate(cell) {
      if (!cell.draft) return "";
      const info = this._info(cell);
      if (!info.compatible) return this._t("incompatible");
      if (!info.available) return this._t("unavailable");
      if (info.format !== cell.draft.format) return this._t("conflict");
      const value = encode(cell.draft.hours, cell.draft.minutes, info.format);
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
        if (c.pending?.accepted && info.available && info.compatible && info.format === c.pending.format && info.value === c.pending.value) {
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
        else if (!c.draft && !info.time) problem = this._t(info.format === "hhmm" ? "invalid_hhmm" : "invalid_bcd", {raw: String(info.raw)});
        c.note.textContent = problem || (c.pending ? (c.pending.accepted ? this._t("waiting") : this._t("sending")) : c.draft ? this._t("modified") : "");
        c.td.toggleAttribute("data-error", Boolean(problem));
        c.td.toggleAttribute("data-dirty", Boolean(c.draft));
        c.hours.setAttribute("aria-invalid", String(Boolean(problem)));
        c.minutes.setAttribute("aria-invalid", String(Boolean(problem)));
        c.raw.textContent = this._config.show_raw && info.available ? `${info.format === "hhmm" ? "HHMM" : "WORD"} ${String(info.raw)}` : "";
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
        const format = this._info(cell).format;
        const value = encode(cell.draft.hours, cell.draft.minutes, format);
        if (this._info(cell).value === value) { cell.draft = null; cell.error = ""; continue; }
        cell.error = "";
        cell.pending = { value, format, accepted: false };
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
      this._bulk = {on: [], off: [], queries: {on: "", off: ""}, open: false};
      this.shadowRoot.addEventListener("focusout", () => queueMicrotask(() => {
        if (this.isConnected && !this.shadowRoot.activeElement && this._needsRender()) this._render();
      }));
    }

    _t(key, values) { return translate(this._hass, key, values); }

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
        .filter(([id]) => /^(number|input_number)\./.test(id))
        .map(([id, state]) => [id, state.attributes?.friendly_name || id])
        .sort((a, b) => a[1].localeCompare(b[1]) || a[0].localeCompare(b[0]));
    }

    _deviceId(id) { return this._hass?.entities?.[id]?.device_id ?? ""; }

    _choices(row, key, options) {
      const used = new Set();
      for (const other of this._config.rows) for (const field of ["on_entity", "off_entity"]) {
        if (other !== row || field !== key) used.add(other[field]);
      }
      return options.filter(([id]) => {
        const state = this._hass.states[id];
        return compatible(state, resolveFormat(state, legacyFieldFormat(this._config, row, key))) &&
          !used.has(id) && (!this._plc || this._deviceId(id) === this._plc);
      });
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
      this._formatHint.textContent = this._t("editor_hint");
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
          const format = resolveFormat(state, legacyFieldFormat(this._config, row, key));
          const isCompatible = compatible(state, format);
          const time = isCompatible ? decode(state?.state, format) : null;
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
      this._refreshBulk(options);
    }

    _bulkAvailable(id) {
      const state = this._hass?.states?.[id];
      return /^(number|input_number)\./.test(id) && Boolean(state) &&
        compatible(state, resolveFormat(state, legacyFormat(this._config))) &&
        !this._config.rows.some(row => row.on_entity === id || row.off_entity === id);
    }

    _bulkMatches(key, entries = this._options()) {
      const other = key === "on" ? "off" : "on", query = this._bulk.queries[key].trim().toLocaleLowerCase();
      const options = new Map(entries);
      for (const id of this._bulk[key]) if (!options.has(id)) options.set(id, id);
      return [...options].filter(([id, name]) =>
        (this._bulk[key].includes(id) || (this._bulkAvailable(id) && !this._bulk[other].includes(id))) &&
        (!this._plc || this._deviceId(id) === this._plc) && `${name} ${id}`.toLocaleLowerCase().includes(query))
        .sort(([a], [b]) => a.localeCompare(b, "en", {numeric: true}));
    }

    _bulkProblem() {
      const {on, off} = this._bulk, ids = [...on, ...off];
      if (new Set(ids).size !== ids.length || ids.some(id => !this._bulkAvailable(id))) return this._t("bulk_invalid");
      return !on.length || on.length !== off.length ? this._t("bulk_incomplete") : "";
    }

    _bulkAdd() {
      // Revalidate at the final click, including changes made in other editor fields.
      if (this._bulkProblem()) { this._refresh(); return; }
      const first = this._config.rows.length;
      const rows = this._bulk.on.map((id, index) => ({name: "", on_entity: id, off_entity: this._bulk.off[index]}));
      this._groups.forEach((g, i) => {this._rowUI[i].open = g.details.open;});
      this._config.rows = [...this._config.rows, ...rows];
      this._rowUI.push(...rows.map((_, index) => ({open: index === 0, queries: {}})));
      this._bulk = {on: [], off: [], queries: {on: "", off: ""}, open: false};
      this._emit(true);
      this._groups[first]?.details.querySelector("summary").focus();
    }

    _buildBulk(field) {
      this._bulkDetails = el("details", "bulk"); this._bulkDetails.open = this._bulk.open;
      this._bulkDetails.addEventListener("toggle", () => {this._bulk.open = this._bulkDetails.open;});
      this._bulkDetails.append(el("summary", "", this._t("bulk_title")));
      const content = el("div", "bulk-content"), columns = el("div", "bulk-columns");
      content.append(el("p", "hint", this._t("bulk_hint")));
      this._bulkUI = {};
      for (const key of ["on", "off"]) {
        const column = el("div", "bulk-column");
        column.append(el("strong", "", this._t(key)));
        const search = field(column, this._t("editor_search"), el("input", `bulk-search-${key}`));
        search.type = "search"; search.value = this._bulk.queries[key]; search.autocomplete = "off";
        search.addEventListener("input", () => {this._bulk.queries[key] = search.value; this._refresh();});
        const actions = el("div", "actions"), all = el("button", `bulk-all-${key}`, this._t("bulk_all"));
        const clear = el("button", `bulk-clear-${key}`, this._t("bulk_clear")); all.type = clear.type = "button";
        all.addEventListener("click", () => {
          this._bulk[key] = [...new Set([...this._bulk[key], ...this._bulkMatches(key).map(([id]) => id)])]
            .sort((a, b) => a.localeCompare(b, "en", {numeric: true}));
          this._refresh();
        });
        clear.addEventListener("click", () => {this._bulk[key] = []; this._refresh();});
        actions.append(all, clear);
        const list = el("div", `bulk-list bulk-list-${key}`); list.setAttribute("role", "group"); list.setAttribute("aria-label", this._t(key));
        column.append(actions, list); columns.append(column); this._bulkUI[key] = {list, all, clear};
      }
      content.append(columns);
      this._bulkCount = el("p", "hint"); this._bulkCount.setAttribute("role", "status");
      this._bulkPreview = el("div", "bulk-preview");
      this._bulkStatus = el("p", "hint"); this._bulkStatus.setAttribute("role", "status");
      this._bulkApply = el("button", "bulk-apply"); this._bulkApply.type = "button";
      this._bulkApply.addEventListener("click", () => this._bulkAdd());
      content.append(this._bulkCount, this._bulkPreview, this._bulkStatus, this._bulkApply);
      this._bulkDetails.append(content); this.shadowRoot.append(this._bulkDetails);
    }

    _refreshBulk(options) {
      if (!this._bulkUI) return;
      for (const key of ["on", "off"]) {
        const {list, all, clear} = this._bulkUI[key], matches = this._bulkMatches(key, options);
        const signature = JSON.stringify(matches.map(([id, name]) => [id, name, this._bulk[key].includes(id)]));
        all.disabled = !matches.some(([id]) => !this._bulk[key].includes(id)); clear.disabled = !this._bulk[key].length;
        if (list._signature === signature) continue;
        list._signature = signature;
        const focusedId = list.contains(this.shadowRoot.activeElement) ? this.shadowRoot.activeElement.dataset.entity : null;
        list.replaceChildren();
        if (!matches.length) list.append(el("p", "hint", this._t("editor_no_results")));
        for (const [id, name] of matches) {
          const label = el("label"), checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = this._bulk[key].includes(id);
          checkbox.dataset.entity = id;
          checkbox.addEventListener("change", () => {
            this._bulk[key] = checkbox.checked ? [...this._bulk[key], id].sort((a, b) => a.localeCompare(b, "en", {numeric: true})) :
              this._bulk[key].filter(value => value !== id);
            this._refresh();
          });
          const text = el("span", "", name); text.append(el("small", "", id)); label.append(checkbox, text); list.append(label);
          if (focusedId === id) checkbox.focus();
        }
      }
      const ids = [...this._bulk.on, ...this._bulk.off], problem = this._bulkProblem();
      this._bulkCount.textContent = this._t("bulk_counts", {on: this._bulk.on.length, off: this._bulk.off.length});
      this._bulkStatus.textContent = problem || this._t("bulk_ready"); this._bulkStatus.classList.toggle("warning", Boolean(problem));
      this._bulkApply.textContent = this._t("bulk_add", {count: this._bulk.on.length}); this._bulkApply.disabled = Boolean(problem);
      const signature = JSON.stringify([this._bulk.on, this._bulk.off, this._config.rows.length,
        ids.map(id => [this._hass?.states?.[id], this._bulkAvailable(id)]), legacyFormat(this._config)]);
      if (this._bulkPreview._signature === signature) return;
      const active = this.shadowRoot.activeElement;
      const focus = this._bulkPreview.contains(active) && active?.classList.contains("bulk-move") ? {...active.dataset} : null;
      this._bulkPreview._signature = signature; this._bulkPreview.replaceChildren();
      if (!ids.length) return;
      const table = el("table"), head = el("thead"), headings = el("tr"), body = el("tbody");
      table.append(el("caption", "", this._t("bulk_preview")));
      for (const key of ["row", "on", "off"]) { const th = el("th", "", this._t(key)); th.scope = "col"; headings.append(th); }
      head.append(headings);
      for (let index = 0; index < Math.max(this._bulk.on.length, this._bulk.off.length); index++) {
        const tr = el("tr"), th = el("th", "", pad(this._config.rows.length + index + 1)); th.scope = "row"; tr.append(th);
        for (const key of ["on", "off"]) {
          const td = el("td"), id = this._bulk[key][index], state = this._hass?.states?.[id];
          if (!id) {td.textContent = "—"; tr.append(td); continue;}
          const valid = this._bulkAvailable(id) && ids.filter(value => value === id).length === 1;
          const time = valid ? decode(state?.state, resolveFormat(state, legacyFormat(this._config))) : null;
          td.append(el("span", "", state?.attributes?.friendly_name || id), el("small", "", id));
          if (time) td.append(el("small", "", `${time.hours}:${time.minutes}`));
          if (!valid) td.append(el("small", "warning", this._t("editor_unavailable")));
          const actions = el("div", "actions");
          for (const delta of [-1, 1]) {
            const button = el("button", "bulk-move", delta < 0 ? "↑" : "↓"); button.type = "button";
            button.dataset.key = key; button.dataset.index = String(index); button.dataset.delta = String(delta);
            button.setAttribute("aria-label", `${this._t(delta < 0 ? "editor_up" : "editor_down")} — ${this._t(key)}: ${id}`);
            button.disabled = index + delta < 0 || index + delta >= this._bulk[key].length;
            button.addEventListener("click", () => {
              const values = this._bulk[key]; [values[index], values[index + delta]] = [values[index + delta], values[index]];
              this._refresh();
              this._bulkPreview.querySelector(`button[data-key="${key}"][data-index="${index + delta}"][data-delta="${-delta}"]`)?.focus();
            });
            actions.append(button);
          }
          td.append(actions); tr.append(td);
        }
        body.append(tr);
      }
      table.append(head, body); this._bulkPreview.append(table);
      if (focus) this._bulkPreview.querySelector(`button[data-key="${focus.key}"][data-index="${focus.index}"][data-delta="${focus.delta}"]:not(:disabled)`)?.focus();
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
        .bulk-content { padding:0 12px 12px; }
        .bulk-columns { display:flex; flex-wrap:wrap; gap:12px; }
        .bulk-column { flex:1 1 180px; min-width:0; }
        .bulk-list { max-height:220px; overflow:auto; margin-top:10px; }
        .bulk-list label { display:flex; align-items:center; gap:8px; min-height:44px; margin:0; padding:4px; }
        .bulk-list input { flex:none; width:20px; height:20px; }
        .bulk small { display:block; font-size:11px; color:var(--secondary-text-color); overflow-wrap:anywhere; }
        .bulk-list span, .bulk-preview td { overflow-wrap:anywhere; }
        .bulk-preview table { width:100%; table-layout:fixed; border-collapse:collapse; font-size:12px; }
        .bulk-preview caption { text-align:left; font-weight:600; margin-bottom:8px; }
        .bulk-preview th, .bulk-preview td { padding:6px; border-bottom:1px solid var(--divider-color,#aaa); vertical-align:top; }
        .bulk-preview th:first-child { width:36px; }
        .bulk-preview .actions { gap:4px; margin-top:4px; }
        .bulk-preview .warning { color:var(--error-color,#c33b39); }
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
      this._buildBulk(field);
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
