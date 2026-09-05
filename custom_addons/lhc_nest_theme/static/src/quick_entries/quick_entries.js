/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Quick Entries hub.
 *
 * The mockup replaces a flat submenu with a launcher of task cards grouped by
 * what the user is trying to do. This builds that grid from the *same*
 * `ir.ui.menu` children the menu already has, so:
 *
 *   - every card dispatches an existing action — nothing new is created here;
 *   - an entry hidden from this user by `groups=` never reaches the browser,
 *     so the Admin-only financial cards are absent for an Accountant rather
 *     than merely hidden;
 *   - adding a tenth quick entry in XML makes a tenth card appear.
 *
 * Sections and blurbs are presentation, keyed on xmlid. An entry with no
 * mapping still renders — it lands in "More", so a new menu is never silently
 * dropped from the hub.
 */

const QUICK_MENU_XMLID = "lhc_nest.menu_lhc_quick";

const SECTIONS = [
    { key: "rent",     icon: "🏠", title: "Rent & Tenancy" },
    { key: "fixtures", icon: "🛋️", title: "Fixtures & Deposits" },
    { key: "expense",  icon: "🔧", title: "Expenses" },
    { key: "admin",    icon: "🔐", title: "Admin Financial" },
    { key: "more",     icon: "➕", title: "More" },
];

const ENTRY_META = {
    "lhc_nest_money.menu_lhc_quick_receipt": {
        section: "rent", icon: "💰", tone: "green",
        desc: "Record rent received from a tenant",
    },
    "lhc_nest_money.menu_lhc_quick_bill": {
        section: "rent", icon: "📄", tone: "blue",
        desc: "Proforma or tax invoice sent ahead of payment",
    },
    "lhc_nest_properties.menu_lhc_quick_book": {
        section: "rent", icon: "📋", tone: "teal",
        desc: "Token advance received — mark the unit booked",
    },
    "lhc_nest_leasing.menu_lhc_quick_advance": {
        section: "fixtures", icon: "💵", tone: "amber",
        desc: "Record a deposit installment received",
    },
    "lhc_nest_properties.menu_lhc_quick_fixture": {
        section: "fixtures", icon: "🛋️", tone: "purple",
        desc: "New fridge, AC, bed — with the vendor bill",
    },
    "lhc_nest_money.menu_lhc_quick_maint": {
        section: "expense", icon: "🔧", tone: "red",
        desc: "Unit repair or building-level expense",
    },
    "lhc_nest_reports.menu_lhc_quick_gstpay": {
        section: "admin", icon: "💸", tone: "amber",
        desc: "Amount your auditor asked you to remit",
    },
    "lhc_nest_reports.menu_lhc_quick_auditor": {
        section: "admin", icon: "👨‍💼", tone: "blue",
        desc: "Professional fee paid to your auditor",
    },
    "lhc_nest_reports.menu_lhc_quick_withdrawal": {
        section: "admin", icon: "🏦", tone: "purple",
        desc: "Money taken out, tracked name-wise",
    },
};

export class LhcQuickEntries extends Component {
    static template = "lhc_nest_theme.QuickEntries";
    static props = ["*"];

    setup() {
        this.menuService = useService("menu");
        this.state = useState({ sections: [] });

        onWillStart(() => {
            this.state.sections = this._build();
        });
    }

    _build() {
        const menu = this.menuService
            .getAll()
            .find((m) => m.xmlid === QUICK_MENU_XMLID);

        if (!menu) {
            return [];
        }

        const tree = this.menuService.getMenuAsTree(menu.id);
        const buckets = {};
        for (const section of SECTIONS) {
            buckets[section.key] = [];
        }

        for (const child of tree.childrenTree || []) {
            if (!child.actionID) {
                continue;
            }
            const meta = ENTRY_META[child.xmlid] || {};
            const key = buckets[meta.section] ? meta.section : "more";
            buckets[key].push({
                id: child.id,
                name: child.name,
                desc: meta.desc || "",
                icon: meta.icon || "▸",
                tone: meta.tone || "gray",
            });
        }

        return SECTIONS
            .map((section) => ({ ...section, entries: buckets[section.key] }))
            .filter((section) => section.entries.length);
    }

    openEntry(entry) {
        this.menuService.selectMenu(entry.id);
    }
}

registry.category("actions").add("lhc_nest_theme.quick_entries", LhcQuickEntries);
