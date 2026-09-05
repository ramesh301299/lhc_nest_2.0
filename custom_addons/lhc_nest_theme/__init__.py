# -*- coding: utf-8 -*-
"""LHC NEST theme.

No models. The only Python here is an uninstall hook.

The theme changes exactly one record it does not own: it points the Quick
Entries menu at its card-grid client action. Odoo deletes the action on
uninstall but does not undo that write, so without the hook the menu would be
left pointing at a record that no longer exists.

(The kanban views this addon used to carry now ship with the addons that own
their models, so there are no view_mode overrides left to undo.)
"""
import logging

_logger = logging.getLogger(__name__)


def uninstall_hook(env):
    """Return Quick Entries to being a plain parent menu."""
    menu = env.ref('lhc_nest.menu_lhc_quick', raise_if_not_found=False)
    if menu:
        menu.action = False
    else:
        _logger.info("LHC theme uninstall: menu_lhc_quick is gone, nothing to restore.")
