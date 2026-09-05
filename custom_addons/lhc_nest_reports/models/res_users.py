# -*- coding: utf-8 -*-
"""Land LHC users on the Dashboard after login.

Odoo already has a first-class mechanism for "which screen does this user get
after signing in": ``res.users.action_id``, the Home Action. Setting it is the
supported way to do this — no controller override, no redirect hack, and the
user keeps the ability to change it from their own preferences.

Without it Odoo falls back to the Apps grid, which is what the LHC users were
landing on.

This is navigation, not business logic: it changes where a session starts, not
what anyone may see or do. Access is still whatever the groups say, and a user
who cannot open the dashboard action simply does not get it set.
"""
from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _lhc_dashboard_action(self):
        return self.env.ref('lhc_nest_reports.action_lhc_dashboard_cards',
                            raise_if_not_found=False)

    @api.model_create_multi
    def create(self, vals_list):
        """A new LHC user starts on the Dashboard too."""
        users = super().create(vals_list)
        action = self._lhc_dashboard_action()
        if action:
            for user in users:
                # Never override a home action someone deliberately chose,
                # and only set it for users who actually have LHC access.
                if not user.action_id and user.has_group('lhc_nest.group_lhc_accountant'):
                    user.sudo().action_id = action.id
        return users


def set_lhc_home_action(env):
    """Point existing LHC users at the Dashboard.

    Called from the post-init hook. Idempotent, and deliberately skips any user
    who already has a home action of their own.
    """
    action = env.ref('lhc_nest_reports.action_lhc_dashboard_cards',
                     raise_if_not_found=False)
    if not action:
        return
    group = env.ref('lhc_nest.group_lhc_accountant', raise_if_not_found=False)
    if not group:
        return
    # group_lhc_admin implies group_lhc_accountant, so this covers both roles.
    for user in group.users:
        if not user.action_id:
            user.sudo().action_id = action.id
