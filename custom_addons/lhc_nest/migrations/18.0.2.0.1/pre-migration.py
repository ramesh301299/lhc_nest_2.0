# -*- coding: utf-8 -*-
"""Let the corrected roles and record rules reach this database.

``security/lhc_groups.xml`` and ``security/lhc_security_rules.xml`` were
originally loaded with ``noupdate="1"``. That flag is stored on the
``ir.model.data`` row, not read from the XML each time, so flipping it in the
source does **not** retroactively make an existing record updatable — Odoo
keeps skipping it, and a security fix sits unapplied on every database that
installed the old version.

Concretely, this is what stopped ``base.group_user`` being added to the two
LHC NEST roles: the write was in the file, the load ran without error, and the
row was skipped. An Accountant-only login stayed a portal user, unable to open
the backend at all.

This clears the flag for this module's security records only — the roles, their
category and its record rules. They are then reloaded by the normal data load
that follows. Billing entities and menus are deliberately untouched: those are
operational data an administrator is expected to edit.
"""
import logging
import os

_logger = logging.getLogger(__name__)

SECURITY_MODELS = ('res.groups', 'ir.module.category', 'ir.rule')


def migrate(cr, version):
    if not version:
        return
    # The module name is the directory three levels up from this file; derived
    # from the path rather than hard-coded, so the same script is correct in
    # every addon that carries it.
    module = os.path.basename(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))))
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = %s
           AND model IN %s
           AND noupdate = TRUE
    """, (module, SECURITY_MODELS))
    if cr.rowcount:
        _logger.info(
            "%s: cleared noupdate on %s security record(s) so the corrected "
            "security model is applied.", module, cr.rowcount)
