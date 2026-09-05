/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

/**
 * Column labels for the mobile card layout.
 *
 * Below 600px `mobile.scss` turns each list row into a card and each cell into
 * a label/value pair. The label comes from `td[data-label]`, which Odoo does
 * not emit — so this copies it off the matching `<th>` after render.
 *
 * Deliberately a DOM observer rather than a patch of ListRenderer: it touches
 * only a presentational attribute, cannot interfere with how Odoo builds or
 * updates the list, and if it fails the table simply falls back to Odoo's own
 * horizontal scroll. It also does nothing at all above the breakpoint.
 */

const PHONE_QUERY = "(max-width: 600px)";

function labelTable(table) {
    const headers = [...table.querySelectorAll("thead th")].map((th) =>
        (th.textContent || "").trim()
    );
    if (!headers.length) {
        return;
    }
    for (const row of table.querySelectorAll("tbody tr")) {
        [...row.children].forEach((cell, i) => {
            const label = headers[i];
            // Skip the selector/actions columns, which have no header text.
            if (label && cell.getAttribute("data-label") !== label) {
                cell.setAttribute("data-label", label);
            }
        });
    }
}

function labelAll(root = document) {
    for (const table of root.querySelectorAll(".o_list_table")) {
        labelTable(table);
    }
}

export const lhcListMobileService = {
    start() {
        const mq = browser.matchMedia(PHONE_QUERY);
        let observer = null;

        const stop = () => {
            if (observer) {
                observer.disconnect();
                observer = null;
            }
        };

        const start = () => {
            if (observer) {
                return;
            }
            labelAll();
            observer = new MutationObserver((records) => {
                // Re-label only the subtrees that actually changed, so a busy
                // list does not turn into a full re-scan on every keystroke.
                for (const rec of records) {
                    for (const node of rec.addedNodes) {
                        if (node.nodeType !== 1) {
                            continue;
                        }
                        if (node.matches?.(".o_list_table")) {
                            labelTable(node);
                        } else {
                            labelAll(node);
                        }
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        };

        const sync = () => (mq.matches ? start() : stop());
        mq.addEventListener("change", sync);
        sync();
    },
};

registry.category("services").add("lhc_nest_theme.list_mobile", lhcListMobileService);
