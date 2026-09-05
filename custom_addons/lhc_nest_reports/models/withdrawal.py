# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcWithdrawal(models.Model):
    """Personal Withdrawals — owner's-drawing ledger, name-wise, Admin only (spec 5.5)."""
    _name = 'lhc.withdrawal'
    _description = 'LHC Personal Withdrawal'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    entity_id = fields.Many2one('lhc.billing.entity', string='Name', required=True,
                                help="FK to billing entities — new entities appear here automatically.", tracking=True)
    amount = fields.Float('Amount (₹)', required=True, tracking=True)
    date = fields.Date('Date', default=fields.Date.context_today, tracking=True)
    note = fields.Char('Purpose / Note')
    entered_by = fields.Many2one('res.users', string='Entered By',
                                 default=lambda s: s.env.user, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.withdrawal') or 'New'
        return super().create(vals_list)
