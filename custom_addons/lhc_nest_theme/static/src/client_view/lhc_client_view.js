/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * LHC NEST client view — the customer-facing screen for an Odoo model.
 *
 * Two ways into the same data:
 *
 *   Odoo Menu   → Odoo's own list/form.   Everything Odoo can do. For developers.
 *   Client View → this component.          The LHC screen. For clients and staff.
 *
 * Nothing here is a copy of Odoo's data or its rules:
 *
 *   - the columns come from the model's real list view (`get_views`);
 *   - the form fields come from its real form view, notebook pages included;
 *   - field types, labels and selection options come from the same call;
 *   - records are read with `web_search_read` and written with `web_save`, so
 *     record rules, access rights, defaults, computes and constraints all apply
 *     exactly as they do in Odoo. A model the user may not read returns an
 *     AccessError here just as it would anywhere else.
 *
 * The model is passed in the action params, so one component serves every
 * screen and adding another is a menu entry, not a new file.
 */

const PAGE_SIZE = 20;
const NAME_SEARCH_LIMIT = 20;
const M2O_DEBOUNCE_MS = 300;

//: Rendered read-only. Editing a one2many properly means an embedded editable
//: sub-list; until that exists it is more honest to show the linked records
//: than to offer an input that silently drops them.
const READ_ONLY_TYPES = new Set(["one2many", "many2many", "binary", "image", "html"]);

//: Widgets that mark a column as chrome rather than content — a drag handle,
//: an activity decoration. Odoo renders them as controls, not data, so a plain
//: table has nothing to show for them.
const CHROME_WIDGETS = new Set([
    "handle", "activity_exception_decoration", "remaining_days_widget",
]);

//: `mail.thread` and `mail.activity.mixin` add these to almost every model to
//: drive the chatter. They are plumbing, never something a client wants in a
//: column, and they are matched by prefix so a new one needs no change here.
const PLUMBING_PREFIXES = ["message_", "activity_", "rating_", "website_message_"];

/**
 * True when a view attribute means "always hidden".
 *
 * Odoo writes this constant three ways in the same arch — `"1"`, `"True"` and
 * `"true"` — because the value is a Python expression serialised into XML.
 * Matching only `"1"` leaves every `column_invisible="True"` field showing,
 * which is how `sequence`, `active` and half a dozen internal flags end up as
 * columns. Anything else is a real condition and is left alone.
 */
function isAlwaysHidden(node, attribute) {
    const value = node.getAttribute(attribute);
    if (value === null) {
        return false;
    }
    const normalised = value.trim().toLowerCase();
    return normalised === "1" || normalised === "true";
}

export class LhcClientView extends Component {
    static template = "lhc_nest_theme.ClientView";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const params = (this.props.action && this.props.action.params) || {};
        this.model = params.model;
        this.title = params.title || this.model;
        this.icon = params.icon || "";

        this.state = useState({
            mode: "list",          // list | form
            loading: true,
            error: null,

            records: [],
            total: 0,
            offset: 0,
            search: "",
            orderBy: null,
            orderAsc: true,

            recordId: null,        // null while creating
            values: {},            // the record being shown or edited
            editing: false,
            saving: false,
            activeTab: 0,
        });

        // Metadata, loaded once. Not reactive — it never changes for a screen.
        this.fields = {};
        this.columns = [];
        this.tabs = [];
        this.searchFields = [];
        this.m2oCache = {};
        this._m2oTimer = null;

        onWillStart(async () => {
            try {
                await this.loadMetadata();
                await this.loadList();
            } catch (error) {
                this.state.error = this._message(error);
            } finally {
                this.state.loading = false;
            }
        });
    }

    // ------------------------------------------------------------------
    // Metadata — read from the model's own views, never hardcoded
    // ------------------------------------------------------------------
    async loadMetadata() {
        const result = await this.orm.call(
            this.model, "get_views",
            [[[false, "list"], [false, "form"]]],
            { options: {} },
        );

        // `models[model]` is a descriptor, not the field map: the fields live
        // one level down under `.fields`. Reading the wrong level leaves every
        // field unknown, which silently empties the column list.
        const info = (result.models && result.models[this.model]) || {};
        this.fields = info.fields || {};

        const listArch = result.views.list && result.views.list.arch;
        const formArch = result.views.form && result.views.form.arch;

        this.columns = this._parseList(listArch);
        this.tabs = this._parseForm(formArch);

        // Search across the visible text columns, so what the user can see is
        // what they can search. Falls back to display_name, which every model
        // has, rather than searching nothing at all.
        this.searchFields = this.columns
            .filter((name) => ["char", "text"].includes((this.fields[name] || {}).type))
            .filter((name) => (this.fields[name] || {}).store !== false);
        if (!this.searchFields.length) {
            this.searchFields = ["display_name"];
        }
    }

    /** Top-level <field> elements of a list arch, in their declared order. */
    _parseList(arch) {
        if (!arch) {
            return ["display_name"];
        }
        const doc = new DOMParser().parseFromString(arch, "text/xml");
        const names = [];
        for (const node of doc.querySelectorAll("field")) {
            const name = node.getAttribute("name");
            if (!name || names.includes(name) || !this.fields[name]) {
                continue;
            }
            // Always-hidden columns are Odoo's way of loading a value the other
            // columns' conditions depend on. A conditional invisible is left
            // alone — hiding it for every row would lose a column that is
            // visible for most of them.
            if (isAlwaysHidden(node, "column_invisible")
                || isAlwaysHidden(node, "invisible")) {
                continue;
            }
            // Odoo starts these columns hidden behind the list's optional-column
            // menu; showing them by default would be noisier than Odoo itself.
            if (node.getAttribute("optional") === "hide") {
                continue;
            }
            if (CHROME_WIDGETS.has(node.getAttribute("widget"))) {
                continue;
            }
            if (PLUMBING_PREFIXES.some((prefix) => name.startsWith(prefix))) {
                continue;
            }
            names.push(name);
        }
        // A very wide list is unreadable on a phone; the rest stay reachable on
        // the record's own screen.
        return names.slice(0, 8);
    }

    /**
     * Form fields grouped by notebook page, so the LHC screen keeps the tabs
     * the model's designer put there instead of one flat wall of inputs.
     */
    _parseForm(arch) {
        if (!arch) {
            return [{ name: "Details", fields: this.columns.slice() }];
        }
        const doc = new DOMParser().parseFromString(arch, "text/xml");
        const seen = new Set();
        const main = [];
        const pages = [];

        for (const node of doc.querySelectorAll("field")) {
            const name = node.getAttribute("name");
            if (!name || seen.has(name) || !this.fields[name]) {
                continue;
            }
            if (isAlwaysHidden(node, "invisible")) {
                continue;
            }
            if (PLUMBING_PREFIXES.some((prefix) => name.startsWith(prefix))) {
                continue;
            }
            // A field inside another field is a column of an embedded subview,
            // not a field of this record.
            if (node.parentElement && node.parentElement.closest("field")) {
                continue;
            }
            seen.add(name);

            const page = node.closest("page");
            if (page) {
                const label = page.getAttribute("string") || "More";
                let bucket = pages.find((p) => p.name === label);
                if (!bucket) {
                    bucket = { name: label, fields: [] };
                    pages.push(bucket);
                }
                bucket.fields.push(name);
            } else {
                main.push(name);
            }
        }

        const tabs = [];
        if (main.length) {
            tabs.push({ name: "General", fields: main });
        }
        tabs.push(...pages.filter((p) => p.fields.length));
        return tabs.length ? tabs : [{ name: "Details", fields: this.columns.slice() }];
    }

    /** What to ask `web_search_read` / `web_save` to send back for each field. */
    _spec(names) {
        const spec = {};
        for (const name of names) {
            const field = this.fields[name];
            if (!field) {
                continue;
            }
            if (field.type === "many2one") {
                spec[name] = { fields: { display_name: {} } };
            } else if (["one2many", "many2many"].includes(field.type)) {
                spec[name] = { fields: { display_name: {} }, limit: 10 };
            } else {
                spec[name] = {};
            }
        }
        return spec;
    }

    // ------------------------------------------------------------------
    // List
    // ------------------------------------------------------------------
    get domain() {
        const query = this.state.search.trim();
        if (!query) {
            return [];
        }
        // OR across the searchable columns: n terms need n-1 leading '|'.
        const domain = [];
        for (let i = 0; i < this.searchFields.length - 1; i++) {
            domain.push("|");
        }
        for (const name of this.searchFields) {
            domain.push([name, "ilike", query]);
        }
        return domain;
    }

    async loadList() {
        const order = this.state.orderBy
            ? `${this.state.orderBy} ${this.state.orderAsc ? "asc" : "desc"}`
            : "";
        const result = await this.orm.call(this.model, "web_search_read", [], {
            domain: this.domain,
            specification: this._spec(this.columns),
            offset: this.state.offset,
            limit: PAGE_SIZE,
            order,
        });
        this.state.records = result.records || [];
        this.state.total = result.length || 0;
    }

    async _reload() {
        this.state.loading = true;
        this.state.error = null;
        try {
            await this.loadList();
        } catch (error) {
            this.state.error = this._message(error);
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.offset = 0;
        this._reload();
    }

    sortBy(name) {
        if (this.state.orderBy === name) {
            this.state.orderAsc = !this.state.orderAsc;
        } else {
            this.state.orderBy = name;
            this.state.orderAsc = true;
        }
        this.state.offset = 0;
        this._reload();
    }

    get pageStart() {
        return this.state.total ? this.state.offset + 1 : 0;
    }

    get pageEnd() {
        return Math.min(this.state.offset + PAGE_SIZE, this.state.total);
    }

    get canPrev() {
        return this.state.offset > 0;
    }

    get canNext() {
        return this.pageEnd < this.state.total;
    }

    prevPage() {
        if (this.canPrev) {
            this.state.offset = Math.max(0, this.state.offset - PAGE_SIZE);
            this._reload();
        }
    }

    nextPage() {
        if (this.canNext) {
            this.state.offset += PAGE_SIZE;
            this._reload();
        }
    }

    // ------------------------------------------------------------------
    // Record
    // ------------------------------------------------------------------
    async openRecord(record) {
        this.state.loading = true;
        this.state.error = null;
        try {
            const names = this.tabs.flatMap((t) => t.fields);
            const result = await this.orm.call(this.model, "web_read", [[record.id]], {
                specification: this._spec(names),
            });
            this.state.values = result[0] || {};
            this.state.recordId = record.id;
            this.state.mode = "form";
            this.state.editing = false;
            this.state.activeTab = 0;
        } catch (error) {
            this.state.error = this._message(error);
        } finally {
            this.state.loading = false;
        }
    }

    async startCreate() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const names = this.tabs.flatMap((t) => t.fields);
            // Ask Odoo for the model's own defaults rather than inventing them.
            const defaults = await this.orm.call(
                this.model, "default_get", [names.filter((n) => this._editable(n))], {});
            this.state.values = defaults || {};
            this.state.recordId = null;
            this.state.mode = "form";
            this.state.editing = true;
            this.state.activeTab = 0;
        } catch (error) {
            this.state.error = this._message(error);
        } finally {
            this.state.loading = false;
        }
    }

    backToList() {
        this.state.mode = "list";
        this.state.recordId = null;
        this.state.values = {};
        this.state.editing = false;
        this._reload();
    }

    startEdit() {
        this.state.editing = true;
    }

    cancelEdit() {
        if (this.state.recordId) {
            this.openRecord({ id: this.state.recordId });
        } else {
            this.backToList();
        }
    }

    setValue(name, value) {
        this.state.values = { ...this.state.values, [name]: value };
    }

    onInput(name, ev) {
        const field = this.fields[name] || {};
        let value = ev.target.value;
        if (field.type === "boolean") {
            value = ev.target.checked;
        } else if (["integer"].includes(field.type)) {
            value = value === "" ? 0 : parseInt(value, 10);
        } else if (["float", "monetary"].includes(field.type)) {
            value = value === "" ? 0 : parseFloat(value);
        }
        this.setValue(name, value);
    }

    /** The payload for web_save: only writable fields, in Odoo's own shapes. */
    _writeValues() {
        const values = {};
        for (const name of this.tabs.flatMap((t) => t.fields)) {
            if (!this._editable(name)) {
                continue;
            }
            const raw = this.state.values[name];
            const field = this.fields[name];
            if (field.type === "many2one") {
                values[name] = raw && raw.id ? raw.id : false;
            } else if (raw === undefined) {
                continue;
            } else {
                values[name] = raw === "" ? false : raw;
            }
        }
        return values;
    }

    async save() {
        this.state.saving = true;
        this.state.error = null;
        try {
            const names = this.tabs.flatMap((t) => t.fields);
            const ids = this.state.recordId ? [this.state.recordId] : [];
            // web_save creates when the id list is empty and writes when it is
            // not, and returns the record read back — so what is shown after a
            // save is what the database actually holds, computes included.
            const result = await this.orm.call(
                this.model, "web_save", [ids, this._writeValues()],
                { specification: this._spec(names) },
            );
            this.state.values = result[0] || {};
            this.state.recordId = this.state.values.id || this.state.recordId;
            this.state.editing = false;
            this.notification.add("Saved.", { type: "success" });
        } catch (error) {
            // Validation and access errors carry a message written for a person;
            // showing it beats replacing it with something vaguer.
            this.state.error = this._message(error);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async deleteRecord() {
        if (!this.state.recordId) {
            return;
        }
        if (!window.confirm("Delete this record? This cannot be undone.")) {
            return;
        }
        try {
            await this.orm.unlink(this.model, [this.state.recordId]);
            this.notification.add("Deleted.", { type: "success" });
            this.backToList();
        } catch (error) {
            const message = this._message(error);
            this.state.error = message;
            this.notification.add(message, { type: "danger" });
        }
    }

    // ------------------------------------------------------------------
    // Many2one picker
    // ------------------------------------------------------------------
    m2oOptions(name) {
        return this.m2oCache[name] || [];
    }

    onM2oInput(name, ev) {
        const term = ev.target.value;
        clearTimeout(this._m2oTimer);
        this._m2oTimer = setTimeout(async () => {
            const relation = (this.fields[name] || {}).relation;
            if (!relation) {
                return;
            }
            try {
                const found = await this.orm.call(relation, "name_search", [], {
                    name: term, limit: NAME_SEARCH_LIMIT,
                });
                this.m2oCache[name] = found.map(([id, label]) => ({ id, label }));
                // name_search results land outside the reactive state, so nudge
                // it to make the datalist re-render.
                this.state.values = { ...this.state.values };
            } catch {
                this.m2oCache[name] = [];
            }
        }, M2O_DEBOUNCE_MS);
    }

    onM2oChange(name, ev) {
        const label = ev.target.value;
        const match = (this.m2oCache[name] || []).find((o) => o.label === label);
        this.setValue(name, match ? { id: match.id, display_name: match.label } : false);
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------
    label(name) {
        return (this.fields[name] || {}).string || name;
    }

    type(name) {
        return (this.fields[name] || {}).type || "char";
    }

    _editable(name) {
        const field = this.fields[name] || {};
        return !field.readonly && !READ_ONLY_TYPES.has(field.type) && name !== "id";
    }

    isEditable(name) {
        return this.state.editing && this._editable(name);
    }

    selectionOptions(name) {
        return (this.fields[name] || {}).selection || [];
    }

    /** One cell or one read-only field, formatted for its type. */
    display(record, name) {
        const field = this.fields[name] || {};
        const value = record[name];

        if (value === false || value === null || value === undefined || value === "") {
            return "—";
        }
        switch (field.type) {
            case "many2one":
                return value.display_name || "—";
            case "one2many":
            case "many2many":
                if (!value.length) {
                    return "—";
                }
                return value.map((r) => r.display_name || `#${r.id}`).join(", ");
            case "boolean":
                return value ? "Yes" : "No";
            case "selection": {
                const option = (field.selection || []).find((o) => o[0] === value);
                return option ? option[1] : value;
            }
            case "monetary":
            case "float":
                return Number(value).toLocaleString(undefined, {
                    minimumFractionDigits: 2, maximumFractionDigits: 2,
                });
            case "integer":
                return Number(value).toLocaleString();
            case "binary":
            case "image":
                return "(file)";
            default:
                return String(value);
        }
    }

    /** The value an <input> should carry, which is not always what is shown. */
    inputValue(name) {
        const value = this.state.values[name];
        if (value === false || value === null || value === undefined) {
            return "";
        }
        if (this.type(name) === "many2one") {
            return value.display_name || "";
        }
        return value;
    }

    get recordTitle() {
        if (!this.state.recordId) {
            return `New ${this.title}`;
        }
        return this.state.values.display_name
            || this.state.values.name
            || `${this.title} #${this.state.recordId}`;
    }

    _message(error) {
        return (error && (error.data?.message || error.message))
            || "Something went wrong. Please try again.";
    }
}

registry.category("actions").add("lhc_client_view", LhcClientView);
