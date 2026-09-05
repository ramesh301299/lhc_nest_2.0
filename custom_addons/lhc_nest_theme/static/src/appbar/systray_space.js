/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

/**
 * Reserve the right amount of room for the systray in the merged app bar.
 *
 * The systray is lifted onto the control-panel row (see appbar.scss), so the
 * control panel needs padding on its right or the pager and view switcher end
 * up underneath it.
 *
 * A hardcoded reserve does not hold: the systray grows with the company name,
 * shrinks on mobile, and any installed app may add an item to it. So its width
 * is measured and published as `--lhc-systray-w`, which the stylesheet uses.
 * Purely presentational — it reads a width and writes a CSS variable.
 */

const VAR = "--lhc-systray-w";
const GAP = 16;

export const lhcSystraySpaceService = {
    start() {
        let frame = null;

        const measure = () => {
            frame = null;
            const systray = document.querySelector(".o_menu_systray");
            const root = document.body;
            if (!systray || !root.classList.contains("lhc-shell")) {
                root.style.removeProperty(VAR);
                return;
            }
            const width = Math.ceil(systray.getBoundingClientRect().width);
            // 0 means the bar is not laid out yet; keep the previous value
            // rather than collapsing the reserve for a frame.
            if (width > 0) {
                root.style.setProperty(VAR, `${width + GAP}px`);
            }
        };

        // Coalesce bursts of mutations into one measurement per frame.
        const schedule = () => {
            if (frame === null) {
                frame = browser.requestAnimationFrame(measure);
            }
        };

        const observer = new MutationObserver(schedule);
        observer.observe(document.body, { childList: true, subtree: true });
        browser.addEventListener("resize", schedule);

        schedule();
    },
};

registry.category("services").add("lhc_nest_theme.systray_space", lhcSystraySpaceService);
