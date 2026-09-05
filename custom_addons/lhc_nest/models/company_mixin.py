# -*- coding: utf-8 -*-
from odoo import fields, models


class LhcCompanyMixin(models.AbstractModel):
    """Company scoping for every top-level LHC business record.

    Defined once and inherited rather than repeated on each model, so all LHC
    records agree on the field name, the default and the string — which is what
    lets a single record-rule pattern in ``security/lhc_multicompany.xml`` cover
    the whole module.

    ``company_id`` is required: a record with no company is visible from every
    company, which is the opposite of what multi-company scoping is for.
    Existing rows are backfilled with the default company when the module is
    upgraded.

    Child/line records do **not** use this mixin. They declare instead::

        company_id = fields.Many2one(related='<parent>.company_id', store=True,
                                     index=True, readonly=True)

    so a line can never drift into a different company from its parent, and
    Odoo derives the recompute dependency itself.
    """
    _name = 'lhc.company.mixin'
    _description = 'LHC company scoping'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company,
        help="Company this record belongs to. Users only see records of the "
             "companies enabled in their company switcher.")
