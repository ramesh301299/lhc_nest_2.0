# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcVacate(models.Model):
    """Vacate Checklist — fixture-by-fixture deduction + settlement (spec 5.2)."""
    _name = 'lhc.vacate'
    _description = 'LHC Vacate Checklist'
    _inherit = ['mail.thread', 'lhc.inr.mixin', 'lhc.company.mixin']
    _order = 'create_date desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    agreement_id = fields.Many2one('lhc.agreement', string='Agreement', required=True)
    unit_id = fields.Many2one(related='agreement_id.unit_id', string='Unit', store=True)
    tenant_id = fields.Many2one(related='agreement_id.primary_tenant_id', string='Tenant', store=True)

    line_ids = fields.One2many('lhc.vacate.line', 'vacate_id', string='Fixture Checklist')

    # Settlement (spec 5.2)
    advance_held = fields.Float('Advance Held', compute='_compute_settlement', store=True)
    rent_pending = fields.Float('Rent Pending')
    maintenance_dues = fields.Float('Maintenance Dues', compute='_compute_settlement', store=True)
    fixture_deduction = fields.Float('Fixture Damage Deduction',
                                     compute='_compute_settlement', store=True)
    net_refund = fields.Float('Net Refund', compute='_compute_settlement', store=True)

    # Other checklist items
    maint_cleared = fields.Boolean('Maintenance Dues Cleared')
    rent_checked = fields.Boolean('Rent Pending Checked')
    key_handover = fields.Boolean('Key Handover Received')
    eb_final_reading = fields.Boolean('EB / Utility Final Reading Noted')

    state = fields.Selection([
        ('draft', 'In Progress'),
        ('done', 'Settled — Vacant'),
    ], string='Status', default='draft', tracking=True)

    @api.model
    def _prepare_for_agreement(self, agreement):
        """Build a checklist from the unit's fixtures (one record, two places)."""
        existing = self.search([('agreement_id', '=', agreement.id), ('state', '=', 'draft')], limit=1)
        if existing:
            return existing
        vacate = self.create({
            'agreement_id': agreement.id,
            'name': self.env['ir.sequence'].next_by_code('lhc.vacate') or 'New',
            'rent_pending': 0.0,
        })
        for fx in agreement.unit_id.fixture_ids:
            self.env['lhc.vacate.line'].create({
                'vacate_id': vacate.id,
                'fixture_id': fx.id,
                'name': fx.name,
                'quantity': fx.quantity,
            })
        return vacate

    @api.depends('line_ids.deduction', 'agreement_id.advance_collected', 'rent_pending',
                 'unit_id')
    def _compute_settlement(self):
        for v in self:
            v.advance_held = v.agreement_id.advance_collected
            v.fixture_deduction = sum(v.line_ids.mapped('deduction'))
            maint = self.env['lhc.maintenance'].search([
                ('unit_id', '=', v.unit_id.id),
                ('payable_by', '=', 'tenant'),
                ('recovery_status', '=', 'pending')])
            v.maintenance_dues = sum(maint.mapped('amount'))
            v.net_refund = (v.advance_held - (v.rent_pending or 0.0)
                            - v.maintenance_dues - v.fixture_deduction)

    def action_mark_vacant(self):
        for v in self:
            v.state = 'done'
            v.agreement_id.state = 'closed'
            v.agreement_id.unit_id.status = 'vacant'


class LhcVacateLine(models.Model):
    _name = 'lhc.vacate.line'
    _description = 'LHC Vacate Checklist Line'

    vacate_id = fields.Many2one('lhc.vacate', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='vacate_id.company_id', store=True,
                                 index=True, readonly=True)
    fixture_id = fields.Many2one('lhc.fixture.purchase', string='Fixture')
    name = fields.Char('Item', required=True)
    quantity = fields.Integer('Qty', default=1)
    move_in_condition = fields.Selection([
        ('new', 'New'), ('good', 'Good'), ('fair', 'Fair'),
    ], string='Move-in Condition', default='good')
    watchman_condition = fields.Selection([
        ('good', 'Good — no deduction'),
        ('fair', 'Fair — no deduction'),
        ('repair', 'Needs Repair'),
        ('damaged', 'Damaged'),
        ('missing', 'Missing / Replacement'),
    ], string='Watchman-Marked Condition', default='good')
    deduction = fields.Float('Deduction (₹)')
    note = fields.Char('Notes')
