# -*- coding: utf-8 -*-
"""Let the corrected ledger-visibility rules reach this database.

``security/lhc_security.xml`` — now merged into ``lhc_security_rules.xml`` —
was originally loaded with ``noupdate="1"``. That flag is stored on the
``ir.model.data`` row, not read from the XML each time, so flipping it in the
source does not retroactively make the two ledger rules updatable: Odoo keeps
skipping them, and a correction to the closed-month domain sits unapplied on
every database that installed the old version.

This clears the flag for this module's ir.rule records only. The rules
themselves are then reloaded by the normal data load that follows.
"""
import logging
import os

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    module = os.path.basename(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))))
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = %s
           AND model = 'ir.rule'
           AND noupdate = TRUE
    """, (module,))
    if cr.rowcount:
        _logger.info(
            "%s: cleared noupdate on %s record rule(s) so the corrected "
            "security model is applied.", module, cr.rowcount)
