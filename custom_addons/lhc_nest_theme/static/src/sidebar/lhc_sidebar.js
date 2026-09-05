/** @odoo-module **/

import { Component, useState, onWillStart, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";

/**
 * LHC NEST sidebar.
 *
 * Renders the LHC NEST application's own `ir.ui.menu` records, taken from
 * Odoo's menu service, and navigates by handing the menu back to that same
 * service. There is no hardcoded menu list and no hardcoded route:
 *
 *   - a menu added in XML appears here with no change to this file;
 *   - a menu hidden by `groups=` never reaches the client, so visibility stays
 *     enforced on the server;
 *   - clicking runs the menu's configured action through the action service,
 *     exactly as the stock navbar does.
 *
 * The component mounts for every app but renders only inside LHC NEST, so
 * Settings and any other app keep their normal Odoo shell.
 */

const LHC_APP_XMLID = "lhc_nest.menu_lhc_root";
const OPEN_GROUP_KEY = "lhc_nest_theme.open_group";

/**
 * Client views — the customer-facing JS screens.
 *
 * Two doors onto the same Odoo data, deliberately kept apart:
 *
 *   "Odoo Menu"   → Odoo's own list and form, every field and button it has.
 *                   Complete, dense, and meant for developers and back office.
 *   "Client View" → the LHC screen, rendered by lhc_client_view.js. The same
 *                   records, the same permissions, the LHC design.
 *
 * `anchor` is an existing Odoo menu that opens the same model. It is how each
 * entry is permission-gated: if the server did not send that menu to this user,
 * the client view for it is not offered either. Access therefore comes from
 * Odoo's own groups — nothing here decides who may see what, and no login,
 * role or group name is hardcoded.
 */
/**
 * Off. The Client View rows are not shown in the sidebar.
 *
 * The screens themselves still work — `lhc_client_view` is a registered client
 * action, and anything that dispatches it gets the LHC-rendered model. Only the
 * sidebar section is withdrawn, because "Odoo Menu" already reaches the same
 * models and two doors to one place was noise.
 *
 * Setting this to true brings the whole section back; nothing else changes.
 */
const SHOW_CLIENT_VIEWS = false;

const CLIENT_VIEWS = [
    { key: "contacts",  label: "Contacts",     icon: "fa-users",
      model: "res.partner",     anchor: "contacts.res_partner_menu_contacts" },
    { key: "users",     label: "Users",        icon: "fa-id-badge",
      model: "res.users",       anchor: "base.menu_action_res_users" },
    // Anchored on the CRM app rather than its Leads menu: "Leads" is a
    // feature flag (crm.group_use_lead) that is off by default, so anchoring
    // there would hide this view on a stock CRM install. crm.lead holds both
    // leads and opportunities either way.
    { key: "leads",     label: "Opportunities", icon: "fa-bullseye",
      model: "crm.lead",        anchor: "crm.crm_menu_root" },
    { key: "orders",    label: "Sales Orders", icon: "fa-file-text-o",
      model: "sale.order",      anchor: "sale.menu_sale_order" },
    { key: "employees", label: "Employees",    icon: "fa-address-card-o",
      model: "hr.employee",     anchor: "hr.menu_hr_employee_user" },
    { key: "projects",  label: "Projects",     icon: "fa-folder-o",
      model: "project.project", anchor: "project.menu_projects" },
    { key: "tasks",     label: "Tasks",        icon: "fa-check-square-o",
      model: "project.task",    anchor: "project.menu_project_management_all_tasks" },
];

// Presentation only. Each menu gets an icon and `ir.ui.menu` has nowhere to put
// one, so the map lives here, keyed on xmlid — a renamed menu label cannot
// break it, and an unmapped menu simply renders without a glyph rather than
// with a broken one.
//
// Font Awesome classes rather than emoji. Emoji are rendered by the platform,
// so the rail looked like a different product on macOS, Windows and Android,
// none of them could take the brand colour, and several had no glyph at the
// weight the others did. Odoo already ships Font Awesome 4.7 in the backend
// bundle, so this costs nothing to load.
const MENU_ICONS = {
    "lhc_nest_reports.menu_lhc_dashboard":      "fa-bar-chart",
    "lhc_nest.menu_lhc_quick":                  "fa-bolt",
    "lhc_nest_properties.menu_lhc_properties":  "fa-building-o",
    "lhc_nest_properties.menu_lhc_units":       "fa-home",
    "lhc_nest_tenants.menu_lhc_tenants":        "fa-user-o",
    "lhc_nest.menu_lhc_entities":               "fa-university",
    "lhc_nest_properties.menu_lhc_fixtures":    "fa-cube",
    "lhc_nest_leasing.menu_lhc_agreements":     "fa-file-text-o",
    "lhc_nest_leasing.menu_lhc_templates":      "fa-files-o",
    "lhc_nest_leasing.menu_lhc_renewals":       "fa-refresh",
    "lhc_nest_leasing.menu_lhc_vacate":         "fa-sign-out",
    "lhc_nest_money.menu_lhc_approvals":        "fa-check-square-o",
    "lhc_nest_money.menu_lhc_dues":             "fa-exclamation-triangle",
    "lhc_nest_money.menu_lhc_ledger":           "fa-book",
    "lhc_nest_leasing.menu_lhc_advances":       "fa-money",
    "lhc_nest_money.menu_lhc_maintenance":      "fa-wrench",
    "lhc_nest_money.menu_lhc_bills":            "fa-file-o",
    "lhc_nest_money.menu_lhc_monthly_run":      "fa-calendar",
    "lhc_nest_reports.menu_lhc_withdrawals":    "fa-credit-card",
    "lhc_nest_reports.menu_lhc_profitability":  "fa-line-chart",
    "lhc_nest_reports.menu_lhc_bank_collection": "fa-bank",
    "lhc_nest_reports.menu_lhc_gst_summary":    "fa-calculator",
    "lhc_nest_reports.menu_lhc_gst_payment":    "fa-paper-plane-o",
    "lhc_nest_reports.menu_lhc_auditor_fee":    "fa-user-circle-o",
    "lhc_nest_reports.menu_lhc_tds":            "fa-percent",
    "lhc_nest_leasing.menu_lhc_photos":         "fa-camera",
    "lhc_nest_tools.menu_lhc_documents":        "fa-folder-open-o",
    "lhc_nest_tools.menu_lhc_audit_trail":      "fa-history",
    "lhc_nest_tools.menu_lhc_wa":               "fa-whatsapp",
    "lhc_nest_tools.menu_lhc_settings":         "fa-cog",
};


// The mockup gives Quick Entries a gold highlight. Same reasoning as above:
// keyed on xmlid, purely visual.
const HIGHLIGHT_MENUS = new Set(["lhc_nest.menu_lhc_quick"]);

export class LhcSidebar extends Component {
    static template = "lhc_nest_theme.Sidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.user = user;

        this.state = useState({
            open: false,           // off-canvas state below the breakpoint
            activeMenuId: null,
            activeClientView: null,
            openGroup: this._loadOpenGroup(),
            isAdmin: false,
            // Bumped to force a re-read of the menu tree when the app changes.
            revision: 0,
        });

        // The role label reflects real group membership. It is read from the
        // server, not inferred in the browser, and it labels access rather
        // than granting it.
        onWillStart(async () => {
            this.state.isAdmin = await this.user.hasGroup("lhc_nest.group_lhc_admin");
        });

        this._onAppChanged = () => {
            this.state.revision++;
            this._syncBodyClass();
        };
        // On a deep link the current app is not known until the first action
        // has loaded, so the shell class is re-synced here as well as on
        // MENUS:APP-CHANGED. Without this, landing directly on an LHC URL
        // renders the sidebar without the matching content offset.
        this._onUiUpdated = () => {
            this._syncActiveMenu();
            this._syncBodyClass();
            this._revealActiveGroup();
        };

        this.env.bus.addEventListener("MENUS:APP-CHANGED", this._onAppChanged);
        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", this._onUiUpdated);

        onWillDestroy(() => {
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", this._onAppChanged);
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", this._onUiUpdated);
            document.body.classList.remove("lhc-shell");
            document.body.classList.remove("lhc-foreign-app");
        });

        this._syncBodyClass();
    }

    // ------------------------------------------------------------------
    // Visibility
    // ------------------------------------------------------------------

    /** True only inside LHC NEST — every other app keeps the stock shell. */
    /** The LHC NEST app menu, whether or not it is the one currently open. */
    get lhcApp() {
        // Touch `revision` so the getters re-run when the app changes.
        void this.state.revision;
        return this.menuService.getApps().find((a) => a.xmlid === LHC_APP_XMLID);
    }

    /**
     * The sidebar stays up for anyone who has LHC NEST, not only while LHC
     * NEST is the open app. Otherwise stepping into Settings or Discuss would
     * drop the navigation entirely and strand the user with no way back.
     */
    get isActive() {
        return Boolean(this.lhcApp);
    }

    /** True while the user is somewhere inside LHC NEST. */
    get inLhcApp() {
        void this.state.revision;
        const cur = this.menuService.getCurrentApp();
        return Boolean(cur && cur.xmlid === LHC_APP_XMLID);
    }

    /**
     * Every other Odoo application this user can reach — Contacts, CRM, Sales,
     * Project, Employees, Settings and anything else installed.
     *
     * Listed under the single "Odoo Menu" entry, and opened as Odoo's own
     * screens: this is the developer / back-office door, where the full Odoo
     * form, every field and every button is available.
     *
     * Built from menuService.getApps(), so it is exactly what the server
     * grants: an app the user may not open never appears, and an uninstalled
     * module contributes nothing. Nothing is hardcoded.
     */
    get odooApps() {
        void this.state.revision;
        return this.menuService
            .getApps()
            .filter((a) => a.xmlid !== LHC_APP_XMLID)
            .map((a) => ({
                id: a.id,
                name: a.name,
                xmlid: a.xmlid,
                actionID: a.actionID,
                webIconData: a.webIconData || false,
            }));
    }

    /**
     * The client-view screens this user may open.
     *
     * Gated on the anchor menu: `getAll()` returns the menus the server sent,
     * so if Odoo withheld the Users menu from this user, the Users client view
     * is not offered either. The gate is Odoo's, not this file's — and it is
     * only the offer that is hidden. The screen itself reads through the ORM,
     * so a user who reached it another way still gets an AccessError.
     */
    get clientViews() {
        void this.state.revision;
        if (!SHOW_CLIENT_VIEWS) {
            return [];
        }
        const available = new Set(
            this.menuService.getAll().map((m) => m.xmlid).filter(Boolean));
        return CLIENT_VIEWS.filter((v) => available.has(v.anchor));
    }

    /** Open a client view. Same action pipeline as every other menu here. */
    openClientView(view) {
        this.state.activeClientView = view.key;
        this.state.activeMenuId = null;
        this.state.open = false;
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "lhc_client_view",
            name: view.label,
            params: { model: view.model, title: view.label, icon: view.icon },
        });
    }

    isClientViewActive(view) {
        return this.state.activeClientView === view.key;
    }

    /**
     * The shell offset lives on <body> rather than on this element, because
     * the sidebar is fixed-position and the webclient it offsets is its
     * sibling. Adding the class here keeps the CSS free of :has().
     */
    _syncBodyClass() {
        document.body.classList.toggle("lhc-shell", this.isActive);
        // `lhc-foreign-app` drops the LHC page wash and gives Odoo's own
        // breadcrumb and section menus back. That is exactly right for the
        // "Odoo Menu" door, which exists to show the real Odoo form.
        //
        // The test is "an app that is not LHC NEST", not "not inside LHC
        // NEST": a client view is a client action with no app of its own, so
        // getCurrentApp() is undefined there and the LHC styling correctly
        // stays on.
        const current = this.menuService.getCurrentApp();
        document.body.classList.toggle(
            "lhc-foreign-app",
            this.isActive && Boolean(current) && current.xmlid !== LHC_APP_XMLID,
        );
    }

    // ------------------------------------------------------------------
    // Menu tree
    // ------------------------------------------------------------------

    get sections() {
        const app = this.lhcApp;
        if (!app) {
            return [];
        }
        // Always the LHC tree, even when another app is open — the point of
        // keeping the sidebar visible is that LHC NEST stays one click away.
        const tree = this.menuService.getMenuAsTree(app.id);
        return (tree.childrenTree || []).map((menu) => this._decorate(menu));
    }

    /**
     * Classify each top-level entry the way the mockup does:
     *
     *   - has an action  → a clickable item (children are reached from the
     *     screen it opens, e.g. the Quick Entries hub);
     *   - no action but has children → a collapsible group header.
     */
    _decorate(menu) {
        const isGroup = !menu.actionID && (menu.childrenTree || []).length > 0;
        return {
            id: menu.id,
            name: menu.name,
            xmlid: menu.xmlid,
            actionID: menu.actionID,
            isGroup,
            icon: MENU_ICONS[menu.xmlid] || "fa-circle-o",
            highlight: HIGHLIGHT_MENUS.has(menu.xmlid),
            children: isGroup
                ? (menu.childrenTree || []).map((child) => ({
                      id: child.id,
                      name: child.name,
                      xmlid: child.xmlid,
                      actionID: child.actionID,
                      icon: MENU_ICONS[child.xmlid] || "fa-circle-o",
                      highlight: HIGHLIGHT_MENUS.has(child.xmlid),
                  }))
                : [],
        };
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    onMenuClick(menu) {
        if (!menu.actionID) {
            return;
        }
        this.state.activeMenuId = menu.id;
        this.state.open = false;
        this.menuService.selectMenu(menu.id);
    }

    /**
     * Keep the highlight honest when navigation did not start here — a
     * dashboard card, a breadcrumb, or a link in a form. Matches the running
     * action against the menu that declares it.
     */
    _syncActiveMenu() {
        const actionId = this.actionService.currentController?.action?.id;
        if (!actionId) {
            return;
        }
        const found = this._findByAction(this.sections, actionId);
        if (found) {
            this.state.activeMenuId = found.id;
            // Navigating by menu leaves the client view; clearing this stops a
            // stale client-view row staying highlighted.
            this.state.activeClientView = null;
        }
    }

    /** Depth-first search for the node whose action is currently running. */
    _findByAction(nodes, actionId) {
        for (const node of nodes) {
            if (node.actionID === actionId) {
                return node;
            }
            const hit = this._findByAction(node.children || [], actionId);
            if (hit) {
                return hit;
            }
        }
        return null;
    }

    /** True when this node, or anything under it, is the open screen. */
    _containsActive(node) {
        for (const child of node.children || []) {
            if (child.id === this.state.activeMenuId || this._containsActive(child)) {
                return true;
            }
        }
        return false;
    }

    /** Open another Odoo app through the same menu service. */
    openApp(app) {
        this.state.open = false;
        this.menuService.selectMenu(app.id);
    }

    isAppActive(app) {
        void this.state.revision;
        const cur = this.menuService.getCurrentApp();
        return Boolean(cur && cur.id === app.id);
    }

    isMenuActive(menu) {
        return this.state.activeMenuId === menu.id;
    }

    /** A collapsed group still shows as active when it holds the open screen. */
    hasActiveChild(section) {
        return this._containsActive(section);
    }

    // ------------------------------------------------------------------
    // Group collapse — presentation state, so it lives in the browser
    // ------------------------------------------------------------------

    _loadOpenGroup() {
        try {
            return browser.localStorage.getItem(OPEN_GROUP_KEY) || null;
        } catch {
            return null;
        }
    }

    _persistOpenGroup() {
        try {
            if (this.state.openGroup) {
                browser.localStorage.setItem(OPEN_GROUP_KEY, this.state.openGroup);
            } else {
                browser.localStorage.removeItem(OPEN_GROUP_KEY);
            }
        } catch {
            // A blocked or full localStorage costs the remembered state, not
            // the navigation. Nothing to recover from.
        }
    }

    isCollapsed(section) {
        return this.state.openGroup !== section.xmlid;
    }

    /**
     * Accordion: exactly one group open at a time.
     *
     * Opening a group implicitly closes whichever was open, because the state
     * is a single xmlid rather than a per-group flag — there is no way to
     * represent two open groups, so they cannot drift out of sync. Clicking
     * the open group closes it, leaving none open.
     */
    toggleGroup(section) {
        this.state.openGroup =
            this.state.openGroup === section.xmlid ? null : section.xmlid;
        this._persistOpenGroup();
    }

    /**
     * Keep the group holding the current screen open, so navigating from a
     * dashboard card or a breadcrumb reveals where you landed instead of
     * leaving every group shut.
     */
    _revealActiveGroup() {
        for (const section of this.sections) {
            if (section.isGroup && this._containsActive(section)) {
                if (this.state.openGroup !== section.xmlid) {
                    this.state.openGroup = section.xmlid;
                    this._persistOpenGroup();
                }
                return;
            }
        }
    }

    // ------------------------------------------------------------------
    // Identity + off-canvas
    // ------------------------------------------------------------------

    get userName() {
        return this.user.name || this.user.login || "";
    }

    get userInitial() {
        return (this.userName.trim()[0] || "?").toUpperCase();
    }

    /**
     * The role shown is derived from the user's real group membership, which
     * is also what enforces access. It is a label for what the server already
     * decided — never a control that changes it.
     */
    get roleLabel() {
        return this.state.isAdmin ? "ADMIN" : "ACCOUNTANT";
    }

    toggleSidebar() {
        this.state.open = !this.state.open;
    }

    closeSidebar() {
        this.state.open = false;
    }
}

registry.category("main_components").add("lhc_nest_theme.Sidebar", {
    Component: LhcSidebar,
    props: {},
});
