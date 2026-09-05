# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class LhcMaintenance(models.Model):
    """Maintenance & building-level expenses (spec 5.3)."""
    _name = 'lhc.maintenance'
    _description = 'LHC Maintenance / Expense'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Reference', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    date = fields.Date('Date', default=fields.Date.context_today)
    scope = fields.Selection([
        ('unit', 'Unit-specific'),
        ('building', 'Building-level'),
    ], string='Scope', default='unit', required=True)

    property_id = fields.Many2one('lhc.property', string='Property', required=True)
    unit_id = fields.Many2one('lhc.unit', string='Unit',
                              domain="[('property_id','=',property_id)]")
    expense_type = fields.Char('Expense Type', required=True, help="Free text — e.g. geyser repair, "
                               "watchman salary, common EB, water tax.")
    vendor = fields.Char('Vendor / Person')
    amount = fields.Float('Amount (₹)', required=True)
    note = fields.Text('Note')

    # Building-level extras
    recurring = fields.Boolean('Recurring', help="e.g. monthly salary vs one-time repaint.")
    split_equally = fields.Boolean('Split Equally Among All Units')

    # Posting entity: unit-specific → unit's entity; building-level → the GST entity
    posted_entity_id = fields.Many2one('lhc.billing.entity', string='Posted To Entity',
                                       compute='_compute_posted_entity', store=True)

    # Tenant recovery (for unit-specific tenant-payable, incl. split children)
    payable_by = fields.Selection([
        ('owner', 'Owner / Entity'),
        ('tenant', 'Tenant'),
    ], string='Payable By', default='owner')
    recovery_status = fields.Selection([
        ('na', 'N/A'),
        ('pending', 'Pending Recovery'),
        ('recovered', 'Recovered'),
    ], string='Recovery Status', compute='_compute_recovery_status',
        store=True, readonly=False)

    is_split = fields.Boolean('Split Child', help="Generated from a building-level split entry.")
    parent_id = fields.Many2one('lhc.maintenance', string='Split Source', ondelete='cascade')
    child_ids = fields.One2many('lhc.maintenance', 'parent_id', string='Split Charges')

    @api.depends('scope', 'unit_id', 'unit_id.current_agreement_id')
    def _compute_posted_entity(self):
        building_entity = self.env['lhc.billing.entity'].building_expense_entity()
        for rec in self:
            if rec.scope == 'building':
                rec.posted_entity_id = building_entity
            elif rec.unit_id and rec.unit_id.current_agreement_id:
                rec.posted_entity_id = rec.unit_id.current_agreement_id.billing_entity_id
            else:
                rec.posted_entity_id = False

    @api.depends('payable_by')
    def _compute_recovery_status(self):
        for rec in self:
            if rec.payable_by == 'tenant' and rec.recovery_status in (False, 'na'):
                rec.recovery_status = 'pending'
            elif rec.payable_by == 'owner':
                rec.recovery_status = 'na'

    @api.onchange('scope')
    def _onchange_scope(self):
        if self.scope == 'building':
            self.unit_id = False
        else:
            self.split_equally = False
            self.recurring = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.maintenance') or 'New'
        records = super().create(vals_list)
        for rec in records:
            if rec.scope == 'building' and rec.split_equally and not rec.is_split:
                rec._create_split_charges()
        return records

    def _create_split_charges(self):
        """Split = Amount ÷ unit count, rounded down; remainder on the FIRST unit
        (spec 5.3). Creates one Pending Recovery tenant charge per unit."""
        self.ensure_one()
        units = self.property_id.unit_ids
        n = len(units)
        if n == 0:
            raise UserError("Property has no units to split across.")
        base = int(self.amount // n)  # rounded down to nearest rupee
        remainder = round(self.amount - base * n, 2)
        for idx, unit in enumerate(units):
            share = base + (remainder if idx == 0 else 0)
            self.create({
                'date': self.date,
                'scope': 'unit',
                'property_id': self.property_id.id,
                'unit_id': unit.id,
                'expense_type': '%s (Split)' % self.expense_type,
                'amount': share,
                'payable_by': 'tenant',
                'recovery_status': 'pending',
                'is_split': True,
                'parent_id': self.id,
                'note': 'Split from building-level %s' % self.name,
            })
