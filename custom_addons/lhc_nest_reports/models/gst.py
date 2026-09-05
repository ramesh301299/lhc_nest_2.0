# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcGstPayment(models.Model):
    """Record GST Paid to Government — reduces liability (spec 5.4)."""
    _name = 'lhc.gst.payment'
    _description = 'LHC GST Payment (Remittance)'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'payment_date desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    entity_id = fields.Many2one('lhc.billing.entity', string='Entity',
                                domain="[('gst_applicable','=',True)]", required=True)
    period = fields.Char('Period')
    payment_date = fields.Date('Payment Date', default=fields.Date.context_today)
    amount = fields.Float('Amount Paid (₹)', required=True)
    challan = fields.Char('Challan / Reference No.')
    proof = fields.Binary('Payment Proof')
    proof_filename = fields.Char('Proof Filename')
    entered_by = fields.Many2one('res.users', default=lambda s: s.env.user, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.gst.payment') or 'New'
        return super().create(vals_list)


class LhcAuditorFee(models.Model):
    """Auditor's professional fee — separate simple entry (spec 5.4)."""
    _name = 'lhc.auditor.fee'
    _description = 'LHC Auditor Fee'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'date desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    amount = fields.Float('Amount (₹)', required=True)
    date = fields.Date('Date Paid', default=fields.Date.context_today)
    note = fields.Char('Note')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.auditor.fee') or 'New'
        return super().create(vals_list)


class LhcGstSummary(models.AbstractModel):
    """Helper for the GST / Non-GST Summary numbers.

    Closing Liability = GST Collected − Input GST Credit − GST Remitted.
    If negative it is a carry-forward credit, not a liability (spec 5.4)."""
    _name = 'lhc.gst.summary'
    _description = 'LHC GST Summary (computed)'

    @api.model
    def entity_summary(self, entity):
        # GST collected from approved receipts
        receipts = self.env['lhc.receipt'].search([
            ('billing_entity_id', '=', entity.id), ('state', '=', 'approved')])
        rent_received = sum(receipts.mapped('rent_amount'))
        gst_collected = sum(receipts.mapped('gst_amount'))
        # Input credit from GST purchase bills (assigned to units under this entity's building)
        input_credit = 0.0
        if entity.also_receives_building or entity.gst_applicable:
            purchases = self.env['lhc.fixture.purchase'].search([('gst_bill', '=', True)])
            input_credit = sum(purchases.mapped('gst_amount'))
        remitted = sum(self.env['lhc.gst.payment'].search(
            [('entity_id', '=', entity.id)]).mapped('amount'))
        closing = gst_collected - input_credit - remitted
        return {
            'rent_received': rent_received,
            'gst_collected': gst_collected,
            'input_credit': input_credit,
            'remitted': remitted,
            'closing_liability': closing if closing > 0 else 0.0,
            'carry_forward_credit': -closing if closing < 0 else 0.0,
        }
