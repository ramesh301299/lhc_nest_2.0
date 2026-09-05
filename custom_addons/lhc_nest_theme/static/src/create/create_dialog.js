/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

/**
 * Creating a record opens a wizard, not a screen.
 *
 * Stock Odoo answers "New" by replacing the list with an empty form. The list
 * is gone, the search facets that got you there are gone, and coming back is a
 * breadcrumb click that discards whatever was typed. For a product whose daily
 * work is "open the rent ledger, add one receipt, carry on", that is the wrong
 * shape: creating a record is a side task, and a side task belongs in a dialog
 * over the work rather than instead of it.
 *
 * So every list and kanban in the backend opens its create form in a modal. On
 * save the list behind it reloads in place, with its domain, its search facets
 * and its scroll position intact.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS DOES NOT CHANGE
 *
 * The form itself. The dialog hosts the model's real form view — the same arch,
 * the same fields, the same onchanges, the same buttons, and the same
 * server-side access rules, which were never a client concern anyway. Nothing
 * is re-implemented and no view is rewritten: this changes where the form is
 * drawn, not what it is. Odoo already knows how to run a form in a dialog —
 * it is what every one2many "Add a line" does — so this is its own path, not a
 * new one.
 *
 * ---------------------------------------------------------------------------
 * THE OPT-OUT, AND WHY IT HAS TO EXIST
 *
 * Some records are not a side task. A form that needs the full width of a
 * screen, or one whose flow leans on the breadcrumb, is worse in a modal — and
 * a global patch with no escape hatch is a global patch that eventually has to
 * be reverted wholesale rather than adjusted.
 *
 * Two ways out, both read from data rather than from a list of model names
 * maintained in this file:
 *
 *   1. `lhc_fullpage_create` in the action context — set it on the window
 *      action, or pass it from the button that opens the list, and that one
 *      screen keeps Odoo's behaviour.
 *   2. FULLPAGE_MODELS below, for the handful of models where the full page is
 *      right everywhere they appear.
 */

/**
 * Models that always create on a full page.
 *
 * Deliberately short, and each entry is a decision rather than a precaution:
 *
 *   res.config.settings   not a record — a settings page in form clothing, and
 *                         "creating" one in a dialog is meaningless.
 *   ir.actions.* / ir.ui  developer surfaces reached from Settings, where the
 *   ir.module.module      full page and its breadcrumb are the point.
 */
const FULLPAGE_MODELS = new Set([
    "res.config.settings",
    "ir.actions.act_window",
    "ir.actions.server",
    "ir.actions.report",
    "ir.ui.view",
    "ir.ui.menu",
    "ir.module.module",
]);

/**
 * FormViewDialog with a class on its `.modal-content`.
 *
 * The dialog service has no hook for adding one, and `FormViewDialog` does not
 * forward `contentClass` to the `Dialog` it renders — so the template is
 * inherited in PRIMARY mode, which produces a second, private template rather
 * than modifying `web.FormViewDialog` for every dialog in Odoo.
 *
 * The class is what dialog.scss keys the create-wizard chrome off, so that
 * chrome cannot leak onto the record dialogs Odoo opens for its own reasons.
 */
class LhcCreateDialog extends FormViewDialog {
    static template = "lhc_nest_theme.CreateDialog";
}

/**
 * True when this controller should open its create form in a dialog.
 *
 * Every test is on state the controller already holds — nothing is fetched, so
 * this costs a click nothing.
 */
function shouldUseCreateDialog(controller) {
    const { resModel, context } = controller.props;

    if (!resModel || FULLPAGE_MODELS.has(resModel)) {
        return false;
    }
    // Per-action opt-out.
    if (context && context.lhc_fullpage_create) {
        return false;
    }
    // The list is itself already inside a dialog — a many2one's "Search more",
    // or a wizard that embeds a list. Stacking a second modal on the first is a
    // maze, and Escape stops meaning one thing.
    if (controller.env.inDialog || controller.env.dialogData) {
        return false;
    }
    // The view says the record cannot be created. Let Odoo raise its own
    // refusal rather than opening a dialog that will fail on save.
    if (controller.props.archInfo?.activeActions?.create === false) {
        return false;
    }
    return true;
}

/** "New · Sites" — the action's own name, not a guess at the model's singular. */
function dialogTitle(controller) {
    const name = controller.env.config?.getDisplayName?.();
    return name ? `${_t("New")} · ${name}` : _t("New");
}

/**
 * Open the model's own form view in a modal.
 *
 * `context` is the controller's, so `default_*` values from the action, from a
 * search-panel filter or from the menu that opened the list all still apply — a
 * receipt created from inside a lease arrives with its lease already set,
 * exactly as it would have on the full page.
 */
function openCreateDialog(controller) {
    // Both controllers already hold the dialog service — the list under
    // `dialogService`, the kanban under `dialog`. Reading whichever is there
    // means neither `setup` has to be patched to add a second reference to a
    // service the controller already has.
    const dialog = controller.dialogService || controller.dialog;
    const context = { ...controller.props.context };
    // Odoo carries the id of the record you came from in the context. On a
    // create form that is a stale pointer at the previous record, and any
    // `default_` computed from it server-side would be wrong.
    delete context.active_id;
    delete context.active_ids;

    dialog.add(LhcCreateDialog, {
        resModel: controller.props.resModel,
        resId: false,
        context,
        title: dialogTitle(controller),
        // A create form is two columns of fields; at Odoo's default width the
        // second column wraps under the first for no reason.
        size: "xl",
        // The list behind the dialog is stale the moment a record is saved.
        onRecordSaved: async () => {
            await controller.model.load();
            controller.model.notify();
        },
    });
}

patch(ListController.prototype, {
    /**
     * `createRecord` is what New, the empty-list call to action and the
     * `o-create` hotkey all funnel through, so patching it here covers every
     * door into creation without touching any of them individually.
     */
    async createRecord({ group } = {}) {
        const list = (group && group.list) || this.model.root;
        // An editable list writes its new record as an inline row. That is not
        // a form being opened, it is a line being typed, and a dialog over it
        // would be the wrong object entirely. Same condition as Odoo's own.
        if (this.editable && !list.isGrouped) {
            return super.createRecord(...arguments);
        }
        if (!shouldUseCreateDialog(this)) {
            return super.createRecord(...arguments);
        }
        openCreateDialog(this);
    },
});

patch(KanbanController.prototype, {
    async createRecord() {
        const { onCreate } = this.props.archInfo;
        // A kanban with quick-create already opens a small inline card at the
        // top of a column — the same idea, done better for that view.
        if (this.canQuickCreate && onCreate === "quick_create") {
            return super.createRecord(...arguments);
        }
        // The view names its own create action. Somebody chose that on purpose;
        // it is usually a wizard already.
        if (onCreate && onCreate !== "quick_create") {
            return super.createRecord(...arguments);
        }
        if (!shouldUseCreateDialog(this)) {
            return super.createRecord(...arguments);
        }
        openCreateDialog(this);
    },
});

export { LhcCreateDialog, shouldUseCreateDialog, openCreateDialog };
