/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * LHC NEST dashboard.
 *
 * Holds no figures of its own: every number comes from
 * `lhc.dashboard.get_dashboard_data`, which runs as the current user, so the
 * counts are already filtered by record rules and the active company. A card
 * also carries the action that opens it, so clicking through lands on the same
 * views the menu uses instead of a list re-invented here.
 */
export class LhcDashboard extends Component {
    static template = "lhc_nest.Dashboard";
    // Client actions are handed `action`/`actionId`/`className` by the action
    // service; accepting them all avoids prop-validation noise in dev mode.
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, data: null, error: null });

        onWillStart(async () => {
            await this.load();
        });
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call("lhc.dashboard", "get_dashboard_data", []);
        } catch (err) {
            // A failed read shows a retry panel instead of an empty dashboard
            // that looks like a business with no properties.
            this.state.error =
                err?.data?.message || err?.message || "Unable to reach the server.";
            this.state.data = null;
        } finally {
            this.state.loading = false;
        }
    }

    /** Indian digit grouping (₹1,84,500), matching the rest of the app. */
    formatAmount(value) {
        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
        }).format(value || 0);
    }

    displayValue(card) {
        return card.monetary ? this.formatAmount(card.value) : card.value;
    }

    cardsIn(group) {
        return (this.state.data?.cards || []).filter((c) => c.group === group);
    }

    /**
     * The 'action' group, rendered as the alert list. Only entries with a
     * non-zero count are shown — an alert reading "0 overdue tenants" is
     * noise, and its absence is what makes the empty state meaningful.
     */
    alertCards() {
        return this.cardsIn("action").filter((c) => Number(c.value) > 0);
    }

    /** Cards are focusable, so they must answer the keyboard too. */
    onCardKeydown(ev, card) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openCard(card);
        }
    }

    onRowKeydown(ev, row) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openAgreement(row);
        }
    }

    /** A card with no action (the user may not run it) stays inert. */
    openCard(card) {
        if (card.action) {
            this.action.doAction(card.action);
        }
    }

    openAgreement(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "lhc.agreement",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("lhc_nest.dashboard", LhcDashboard);
