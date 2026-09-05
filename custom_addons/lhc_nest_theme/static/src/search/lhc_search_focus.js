/**
 * LHC NEST — the search box does not steal focus on load.
 *
 * Odoo's control panel renders `<SearchBar autofocus="firstLoad"/>`, so the
 * caret lands in the search field every time a view opens. On a data-entry
 * product that is the wrong default: the first thing you do on most screens is
 * read the list or reach for New, and an already-focused search box means the
 * first key you press starts filtering instead of doing what you meant. It
 * also puts the keyboard up on a tablet before anyone has asked to search.
 *
 * This is NOT a patch of the SearchBar. Odoo already publishes a switch for
 * exactly this — `env.config.disableSearchBarAutofocus`, which SearchBar reads
 * in its own setup:
 *
 *     this.inputRef =
 *         this.env.config.disableSearchBarAutofocus || !this.props.autofocus
 *             ? useRef("autofocus")
 *             : useAutofocus({ mobile: this.ui.isSmall });
 *
 * `getDefaultConfig()` ships it as `false`. Flipping it on the View's sub-env
 * turns it on for every view type — list, kanban, form, pivot, calendar — from
 * one place, using Odoo's own supported route rather than fighting the
 * component. Nothing else about the search bar changes: clicking it, the
 * keyboard shortcut, and the "focus-search" bus event all still focus it.
 */
import { patch } from "@web/core/utils/patch";
import { View } from "@web/views/view";

patch(View.prototype, {
    setup() {
        super.setup(...arguments);
        // After super.setup(), `this.env` is the sub-env View created with
        // `useSubEnv`, so this reaches the SearchBar rendered beneath it.
        this.env.config.disableSearchBarAutofocus = true;
    },
});
