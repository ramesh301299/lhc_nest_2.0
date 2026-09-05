# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
# calculate_billing() and get_gst_rate() live in the base addon with
# lhc.billing.entity, which is the single source of truth for GST. Imported
# absolutely because billing_entity is no longer a sibling module — and
# deliberately imported rather than reimplemented, so receipts, bills and
# the GST report can never drift apart on the rate.
from odoo.addons.lhc_nest.models.billing_entity import calculate_billing, get_gst_rate


class LhcReceipt(models.Model):
    _name = 'lhc.receipt'
    _description = 'LHC Rent Receipt'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'lhc.inr.mixin', 'lhc.company.mixin']
    _order = 'receipt_date desc, id desc'

    name = fields.Char('Receipt No.', copy=False, readonly=True, default='New', tracking=True)
    active = fields.Boolean(default=True)  # cancelled receipts keep their number (spec 4.6)

    agreement_id = fields.Many2one('lhc.agreement', string='Agreement', required=True, tracking=True)
    tenant_id = fields.Many2one(related='agreement_id.primary_tenant_id', string='Tenant', store=True)
    unit_id = fields.Many2one(related='agreement_id.unit_id', string='Unit', store=True)
    property_id = fields.Many2one(related='agreement_id.property_id', string='Property', store=True)
    billing_entity_id = fields.Many2one(related='agreement_id.billing_entity_id',
                                        string='Entity', store=True)
    gst_applicable = fields.Boolean(related='billing_entity_id.gst_applicable', store=True)

    receipt_date = fields.Date('Receipt Date', default=fields.Date.context_today, required=True)
    period = fields.Char('Period', help="e.g. June 2025")
    payment_mode = fields.Selection([
        ('cash', 'Cash'), ('upi', 'UPI'), ('neft', 'NEFT/IMPS'), ('cheque', 'Cheque'),
    ], string='Payment Mode', default='upi')

    # Bank received in — defaults to the agreement's own bank, flags wrong bank
    bank_label = fields.Char('Bank Received In')
    other_bank = fields.Boolean('Received in Other Bank')
    other_bank_reason = fields.Char('Reason for Other Bank')
    wrong_bank_flag = fields.Boolean('Wrong Bank Flag', compute='_compute_wrong_bank', store=True)

    # Amounts — three separate stored fields, never pre-summed (spec 5.12)
    rent_amount = fields.Float('Rent Amount (₹)')
    gst_amount = fields.Float('GST (₹)', compute='_compute_amounts', store=True, readonly=False)
    maintenance_amount = fields.Float('Maintenance Recovery (₹)',
                                      compute='_compute_amounts', store=True)
    total_invoice = fields.Float('Total Invoice (₹)', compute='_compute_amounts', store=True)
    gst_rate = fields.Float('GST Rate %', compute='_compute_amounts')

    maintenance_ids = fields.Many2many('lhc.maintenance', string='Bundled Maintenance',
                                       domain="[('unit_id','=',unit_id),"
                                              "('payable_by','=','tenant'),"
                                              "('recovery_status','=','pending')]")

    # TDS (spec 5.11)
    tds_applicable = fields.Boolean('TDS Deducted by Tenant?')
    tds_amount = fields.Float('TDS Amount (₹)')
    tds_challan = fields.Char('TDS Challan / Cert. No.')

    amount_received_bank = fields.Float('Amount Received in Bank (₹)',
                                        compute='_compute_amounts', store=True, readonly=False)
    partial = fields.Boolean('Partial Payment', compute='_compute_partial', store=True)
    shortfall = fields.Float('Shortfall (₹)', compute='_compute_partial', store=True)

    receipt_type = fields.Char('Receipt Type', compute='_compute_receipt_type', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    posted_by = fields.Many2one('res.users', string='Posted By', default=lambda s: s.env.user)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)

    @api.depends('gst_applicable')
    def _compute_receipt_type(self):
        for r in self:
            r.receipt_type = 'GST Tax Invoice' if r.gst_applicable else 'Non-GST Rent Receipt'

    @api.depends('rent_amount', 'billing_entity_id', 'maintenance_ids.amount')
    def _compute_amounts(self):
        for r in self:
            maint = sum(r.maintenance_ids.mapped('amount'))
            res = calculate_billing(r.env, r.rent_amount, r.billing_entity_id, maint)
            r.gst_amount = res['gst_amount']
            r.maintenance_amount = res['maintenance']
            r.total_invoice = res['total']
            r.gst_rate = get_gst_rate(r.env) if res['gst_applicable'] else 0.0
            # Bank credit defaults to total minus TDS (spec 5.11)
            r.amount_received_bank = res['total'] - (r.tds_amount if r.tds_applicable else 0.0)

    @api.depends('amount_received_bank', 'total_invoice', 'tds_amount', 'tds_applicable')
    def _compute_partial(self):
        for r in self:
            settled = r.amount_received_bank + (r.tds_amount if r.tds_applicable else 0.0)
            r.shortfall = max(0.0, r.total_invoice - settled)
            # TDS is not a shortfall (spec 5.11)
            r.partial = r.shortfall > 0.009

    @api.depends('other_bank', 'other_bank_reason')
    def _compute_wrong_bank(self):
        for r in self:
            r.wrong_bank_flag = r.other_bank

    @api.onchange('agreement_id')
    def _onchange_agreement(self):
        if self.agreement_id:
            self.rent_amount = self.agreement_id.payable_rent
            self.bank_label = self.agreement_id.bank_label

    @api.onchange('tds_applicable')
    def _onchange_tds(self):
        if not self.tds_applicable:
            self.tds_amount = 0.0
            self.tds_challan = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._assign_and_route()
        return records

    def _assign_and_route(self):
        """Assign number & route by role: Admin posts final, Accountant → pending."""
        self.ensure_one()
        if self.name in (False, 'New'):
            seq = 'lhc.gst.invoice' if self.gst_applicable else 'lhc.receipt.nongst'
            self.name = self.env['ir.sequence'].next_by_code(seq) or 'New'
        if self.state != 'draft':
            return
        if self.env.user.has_group('lhc_nest.group_lhc_admin'):
            self.action_approve()
        else:
            self.state = 'pending'

    def action_submit(self):
        for r in self:
            r.state = 'pending'

    def action_approve(self):
        if not self.env.user.has_group('lhc_nest.group_lhc_admin'):
            raise UserError("Only an Admin can approve receipts.")
        for r in self:
            r.state = 'approved'
            r.approved_by = self.env.user
            # Flip bundled maintenance to recovered (spec 5.6)
            r.maintenance_ids.filtered(lambda m: m.payable_by == 'tenant').write(
                {'recovery_status': 'recovered'})
            r._post_ledger()

    def action_reject(self):
        if not self.env.user.has_group('lhc_nest.group_lhc_admin'):
            raise UserError("Only an Admin can reject receipts.")
        self.write({'state': 'rejected'})

    def action_cancel(self):
        # Soft: keep the number, never reuse (spec 4.6)
        self.write({'state': 'cancelled', 'active': False})

    def _post_ledger(self):
        """Post ledger credits. TDS becomes a separate credit entry so the
        balance zeroes out correctly (spec 5.11)."""
        Ledger = self.env['lhc.ledger.entry']
        for r in self:
            Ledger.create({
                'agreement_id': r.agreement_id.id,
                'date': r.receipt_date,
                'entry_type': 'receipt',
                'description': 'Rent Receipt %s' % (r.period or ''),
                'receipt_no': r.name,
                'credit': r.amount_received_bank,
                'receipt_id': r.id,
            })
            if r.tds_applicable and r.tds_amount:
                Ledger.create({
                    'agreement_id': r.agreement_id.id,
                    'date': r.receipt_date,
                    'entry_type': 'tds',
                    'description': 'TDS Credited (challan %s)' % (r.tds_challan or '-'),
                    'receipt_no': r.name,
                    'credit': r.tds_amount,
                    'receipt_id': r.id,
                })


class LhcLedgerEntry(models.Model):
    _name = 'lhc.ledger.entry'
    _description = 'LHC Tenant Ledger Entry'
    _order = 'date, id'

    agreement_id = fields.Many2one('lhc.agreement', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='agreement_id.company_id', store=True,
                                 index=True, readonly=True)
    tenant_id = fields.Many2one(related='agreement_id.primary_tenant_id', store=True)
    unit_id = fields.Many2one(related='agreement_id.unit_id', store=True)
    date = fields.Date('Date', default=fields.Date.context_today)
    entry_type = fields.Selection([
        ('due', 'Rent Due'),
        ('receipt', 'Receipt'),
        ('tds', 'TDS Credited'),
        ('adjust', 'Adjustment'),
    ], string='Type', default='receipt')
    description = fields.Char('Description')
    receipt_no = fields.Char('Receipt No.')
    receipt_id = fields.Many2one('lhc.receipt', ondelete='set null')
    debit = fields.Float('Debit')
    credit = fields.Float('Credit')
    is_closed_month = fields.Boolean('Closed Month',
                                     help="Fully cleared, no dues — archived from Accountant view.")
