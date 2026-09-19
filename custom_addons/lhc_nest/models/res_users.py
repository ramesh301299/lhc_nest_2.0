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

#: Profile fields an LHC NEST user may read and write on their *own* record,
#: on top of the ones Odoo already allows (name, email, image_1920, lang, tz,
#: signature...).
#:
#: Both are delegated from ``res.partner`` through the ``_inherits`` link, so
#: writing them here updates the same partner record the web client writes.
#: ``function`` is Odoo's "Job Position" and is what both front ends label
#: "Designation".
#:
#: This is the one definition of "what a user may change about themselves".
#: The Odoo Preferences dialog and ``POST /api/mobile/profile`` both go through
#: ``res.users.write()``, which reads these lists — so the web app and the
#: mobile app cannot drift apart on which fields are self-service, and neither
#: of them needs ``sudo()`` to offer them.
LHC_SELF_PROFILE_FIELDS = ['phone', 'function']


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # Self-service profile
    # ------------------------------------------------------------------
    @property
    def SELF_READABLE_FIELDS(self):
        """Odoo's own list, plus the two LHC NEST profile fields.

        Overriding the property is the documented extension point — the base
        implementation says so in its own docstring — so this survives an Odoo
        upgrade that adds fields of its own to the list.
        """
        return super().SELF_READABLE_FIELDS + LHC_SELF_PROFILE_FIELDS

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """See :data:`LHC_SELF_PROFILE_FIELDS`.

        ``res.users.write()`` only escalates to superuser when *every* key in
        the write is on this list; anything else falls back to the caller's own
        access rights. Adding a field here is therefore the whole permission
        change — no controller may hand itself more than this.
        """
        return super().SELF_WRITEABLE_FIELDS + LHC_SELF_PROFILE_FIELDS

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
