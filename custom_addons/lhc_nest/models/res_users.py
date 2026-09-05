# -*- coding: utf-8 -*-
"""LHC NEST additions to users: the role a login holds.

The role lived as a module-level ``_user_role()`` in ``controllers/main.py``,
which meant the web controller, the mobile API and any future consumer each
reached into a controller module to answer a question about a *user*. It is a
property of the user record, so it is declared here and the controller
delegates — one definition, and the answer cannot drift between the Odoo
backend, ``/lhc/data/*`` and ``/api/mobile``.
"""
from odoo import _, api, models
from odoo.exceptions import AccessError

ADMIN_GROUP = 'lhc_nest.group_lhc_admin'
ACCT_GROUP = 'lhc_nest.group_lhc_accountant'


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # Role, as the front ends ask for it
    # ------------------------------------------------------------------
    def _lhc_role(self):
        """``'admin'`` or ``'accountant'`` — the role token the UIs switch on.

        Admin implies Accountant, so the admin test has to come first.
        """
        self.ensure_one()
        return 'admin' if self.has_group(ADMIN_GROUP) else 'accountant'

    def _lhc_is_user(self):
        """True when this login is an LHC NEST user *in this database*.

        The registry check is not redundant. On a shared multi-db server Odoo
        loads a controller override process-wide, so an ``/web`` request for an
        unrelated database runs LHC NEST code too. If the LHC models are not in
        this database's registry the addon is not installed here, and no login
        of this database is an LHC NEST user.
        """
        self.ensure_one()
        if 'lhc.unit' not in self.env.registry:
            return False
        return self.has_group(ADMIN_GROUP) or self.has_group(ACCT_GROUP)

    def _lhc_role_labels(self):
        """Human names of the LHC NEST roles this user holds, for messages."""
        self.ensure_one()
        labels = []
        for xmlid, label in (
            (ADMIN_GROUP, _("Admin")),
            (ACCT_GROUP, _("Accountant")),
        ):
            if self.has_group(xmlid):
                labels.append(label)
        return labels

    # ------------------------------------------------------------------
    # Friendly permission errors
    # ------------------------------------------------------------------
    @api.model
    def lhc_raise_module_lockout(self, module_label, allowed_roles):
        """Raise an access error written for an accountant, not a developer.

        The client renders an AccessError in a dialog rather than as a crash,
        so a blocked screen can explain *why* it is blocked and who to ask.
        """
        raise AccessError(_(
            "You can't view %(module)s.\n\n"
            "You're signed in as %(role)s. This isn't an error — it's your "
            "permission level. %(module)s is available to %(allowed)s.\n\n"
            "Ask an administrator if you believe you should have access.",
            module=module_label,
            role=", ".join(self.env.user._lhc_role_labels()) or _("an internal user"),
            allowed=allowed_roles,
        ))
