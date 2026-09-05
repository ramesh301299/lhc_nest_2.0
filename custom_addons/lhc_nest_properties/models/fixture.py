# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcFixturePurchase(models.Model):
    """One record referenced in two places — Agreement→Fixtures tab and the
    unit's Vacate Checklist — never copied data (spec 5.1)."""
    _name = 'lhc.fixture.purchase'
    _description = 'LHC Fixture Purchase'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'purchase_date desc, id desc'

    name = fields.Char('Item Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    quantity = fields.Integer('Qty', default=1)
    purchase_date = fields.Date('Purchase Date', default=fields.Date.context_today)
    cost_before_gst = fields.Float('Cost — Before GST (₹)')

    gst_bill = fields.Boolean('Vendor gave a GST bill?')
    # Entered exactly as printed on the vendor's bill (rates vary by HSN — do not recompute)
    gst_amount = fields.Float('GST Amount on Bill (₹)',
                              help="Input GST Credit against the GST entity's liability.")
    vendor = fields.Char('Vendor')
    bill_file = fields.Binary('Bill / Invoice')
    bill_filename = fields.Char('Bill Filename')

    unit_id = fields.Many2one('lhc.unit', string='Assigned Unit', tracking=True)
    property_id = fields.Many2one(related='unit_id.property_id', store=True, string='Property')

    # Condition tracking used by Agreement fixtures tab / Vacate checklist
    move_in_condition = fields.Selection([
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
    ], string='Condition at Move-in', default='new')

    status = fields.Selection([
        ('assigned', 'Assigned'),
        ('unassigned', 'Awaiting Assignment'),
    ], string='Status', compute='_compute_status', store=True)

    @api.depends('unit_id')
    def _compute_status(self):
        for rec in self:
            rec.status = 'assigned' if rec.unit_id else 'unassigned'

    @api.onchange('gst_bill')
    def _onchange_gst_bill(self):
        if not self.gst_bill:
            self.gst_amount = 0.0
