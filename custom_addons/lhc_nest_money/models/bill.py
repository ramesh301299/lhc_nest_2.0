# -*- coding: utf-8 -*-
from odoo import api, fields, models
# calculate_billing() and get_gst_rate() live in the base addon with
# lhc.billing.entity, which is the single source of truth for GST. Imported
# absolutely because billing_entity is no longer a sibling module — and
# deliberately imported rather than reimplemented, so receipts, bills and
# the GST report can never drift apart on the rate.
from odoo.addons.lhc_nest.models.billing_entity import calculate_billing, get_gst_rate


class LhcBill(models.Model):
    """Bill Before Payment — Proforma (PRO/) & Tax Invoice (GST/) (spec 5.6)."""
    _name = 'lhc.bill'
    _description = 'LHC Bill Before Payment'
    _inherit = ['mail.thread', 'lhc.inr.mixin', 'lhc.company.mixin']
    _order = 'create_date desc'

    name = fields.Char('Doc No.', copy=False, readonly=True, default='New', tracking=True)
    active = fields.Boolean(default=True)
    doc_type = fields.Selection([
        ('proforma', 'Proforma Invoice'),
        ('tax', 'Tax Invoice (before payment)'),
    ], string='Doc Type', default='proforma', required=True, tracking=True)

    agreement_id = fields.Many2one('lhc.agreement', string='Agreement', required=True)
    tenant_id = fields.Many2one(related='agreement_id.primary_tenant_id', string='Tenant', store=True)
    unit_id = fields.Many2one(related='agreement_id.unit_id', string='Unit', store=True)
    billing_entity_id = fields.Many2one(related='agreement_id.billing_entity_id',
                                        string='Entity', store=True)
    gst_applicable = fields.Boolean(related='billing_entity_id.gst_applicable', store=True)

    period = fields.Char('Period')
    rent_amount = fields.Float('Rent Amount (₹)')
    maintenance_ids = fields.Many2many('lhc.maintenance', string='Bundled Maintenance',
                                       domain="[('unit_id','=',unit_id),"
                                              "('payable_by','=','tenant'),"
                                              "('recovery_status','=','pending')]")
    gst_amount = fields.Float('GST (₹)', compute='_compute_amounts', store=True)
    maintenance_amount = fields.Float('Maintenance (₹)', compute='_compute_amounts', store=True)
    total = fields.Float('Total (₹)', compute='_compute_amounts', store=True)
    gst_rate = fields.Float('GST Rate %', compute='_compute_amounts')
    note = fields.Text('Note')

    state = fields.Selection([
        ('awaiting', 'Awaiting Payment'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='awaiting', tracking=True)
    receipt_id = fields.Many2one('lhc.receipt', string='Receipt', readonly=True, copy=False)

    @api.depends('rent_amount', 'billing_entity_id', 'maintenance_ids.amount')
    def _compute_amounts(self):
        for b in self:
            maint = sum(b.maintenance_ids.mapped('amount'))
            res = calculate_billing(b.env, b.rent_amount, b.billing_entity_id, maint)
            b.gst_amount = res['gst_amount']
            b.maintenance_amount = res['maintenance']
            b.total = res['total']
            b.gst_rate = get_gst_rate(b.env) if res['gst_applicable'] else 0.0

    @api.onchange('agreement_id')
    def _onchange_agreement(self):
        if self.agreement_id:
            self.rent_amount = self.agreement_id.payable_rent

    @api.onchange('doc_type', 'gst_applicable')
    def _onchange_doc_type(self):
        # A Proforma can go to anyone; a Tax Invoice is GST-only
        if self.doc_type == 'tax' and not self.gst_applicable:
            self.doc_type = 'proforma'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name in (False, 'New'):
                # Proforma keeps its own PRO/ series; Tax Invoice issued directly in
                # the real GST/ series from creation and carried through (spec 5.13)
                seq = 'lhc.gst.invoice' if rec.doc_type == 'tax' else 'lhc.bill.proforma'
                rec.name = rec.env['ir.sequence'].next_by_code(seq) or 'New'
        return records

    def action_mark_paid(self):
        """Creates the receipt against this same document — never a second number."""
        self.ensure_one()
        receipt = self.env['lhc.receipt'].create({
            'agreement_id': self.agreement_id.id,
            'receipt_date': fields.Date.context_today(self),
            'period': self.period,
            'rent_amount': self.rent_amount,
            'maintenance_ids': [(6, 0, self.maintenance_ids.ids)],
        })
        # For a Tax Invoice, the same GST/ number carries through
        if self.doc_type == 'tax':
            receipt.name = self.name
        self.write({'state': 'paid', 'receipt_id': receipt.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lhc.receipt',
            'res_id': receipt.id,
            'view_mode': 'form',
        }

    @api.model
    def action_generate_monthly_run(self):
        """Monthly Billing Run — backend-only: computes amounts, assigns numbers,
        never sends anything (spec 5.6)."""
        agreements = self.env['lhc.agreement'].search([('state', '=', 'active')])
        created = self.env['lhc.bill']
        for agr in agreements:
            doc_type = 'tax' if agr.gst_applicable else 'proforma'
            created |= self.create({
                'agreement_id': agr.id,
                'doc_type': doc_type,
                'period': fields.Date.context_today(self).strftime('%B %Y'),
                'rent_amount': agr.payable_rent,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Monthly Billing Run',
            'res_model': 'lhc.bill',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }
