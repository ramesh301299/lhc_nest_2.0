# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcBooking(models.Model):
    """Book a Unit — token advance received, mark unit Booked (spec 4.3)."""
    _name = 'lhc.booking'
    _description = 'LHC Unit Booking'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'date_received desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    unit_id = fields.Many2one('lhc.unit', string='Unit', required=True,
                              domain="[('status','=','vacant')]")
    prospect_name = fields.Char('Prospective Tenant Name', required=True)
    phone = fields.Char('Phone')
    token_amount = fields.Float('Token Amount (₹)')
    date_received = fields.Date('Date Received', default=fields.Date.context_today)
    mode = fields.Selection([
        ('cash', 'Cash'), ('upi', 'UPI'), ('neft', 'NEFT/IMPS'), ('cheque', 'Cheque'),
    ], string='Mode', default='upi')
    note = fields.Text('Note')
    state = fields.Selection([
        ('booked', 'Booked'), ('converted', 'Converted'), ('cancelled', 'Cancelled'),
    ], default='booked', string='Status')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.booking') or 'New'
        records = super().create(vals_list)
        for rec in records:
            if rec.unit_id and rec.unit_id.status == 'vacant':
                rec.unit_id.status = 'booked'
        return records
