# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcAdvanceInstallment(models.Model):
    """Advance / security deposit collected in 1–3 installments (spec 4.5).
    Total is fixed at agreement creation; each installment recorded as received."""
    _name = 'lhc.advance.installment'
    _description = 'LHC Advance Installment'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'date, id'

    agreement_id = fields.Many2one('lhc.agreement', string='Agreement', required=True,
                                   ondelete='cascade')
    tenant_id = fields.Many2one(related='agreement_id.primary_tenant_id', string='Tenant', store=True)
    unit_id = fields.Many2one(related='agreement_id.unit_id', string='Unit', store=True)
    installment_no = fields.Integer('Installment No.', default=1)
    amount = fields.Float('Amount Received (₹)', required=True, tracking=True)
    date = fields.Date('Date Received', default=fields.Date.context_today, tracking=True)
    mode = fields.Selection([
        ('cash', 'Cash'), ('upi', 'UPI'), ('neft', 'NEFT/IMPS'), ('cheque', 'Cheque'),
    ], string='Mode of Payment', default='upi', tracking=True)
    reference = fields.Char('Reference / Receipt No.')
