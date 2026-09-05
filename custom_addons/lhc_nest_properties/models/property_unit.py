# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcProperty(models.Model):
    _name = 'lhc.property'
    _description = 'LHC Property / Building'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'name'

    name = fields.Char('Property Name', required=True, tracking=True)
    code = fields.Char('Code', copy=False, readonly=True, default='New')
    active = fields.Boolean(default=True)
    property_type = fields.Selection([
        ('multi', 'Multi-unit'),
        ('commercial', 'Commercial'),
        ('independent', 'Independent / Villa'),
    ], string='Type', default='multi', required=True, tracking=True)
    location = fields.Char('Location')
    # Common EB (shared connection) — distinct from each unit's own EB (spec 5.9)
    common_eb_no = fields.Char('Common EB Service No.',
                               help="Building's shared connection — lift, common lights, pump.")

    unit_ids = fields.One2many('lhc.unit', 'property_id', string='Units')
    unit_count = fields.Integer('Units', compute='_compute_counts')
    occupied_count = fields.Integer('Occupied', compute='_compute_counts')
    vacant_count = fields.Integer('Vacant', compute='_compute_counts')

    @api.depends('unit_ids', 'unit_ids.status')
    def _compute_counts(self):
        for prop in self:
            units = prop.unit_ids
            prop.unit_count = len(units)
            prop.occupied_count = len(units.filtered(lambda u: u.status == 'occupied'))
            prop.vacant_count = len(units.filtered(lambda u: u.status == 'vacant'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('lhc.property') or 'New'
        records = super().create(vals_list)
        # Independent house/villa: auto-create one default unit (spec 4.3)
        for prop in records:
            if prop.property_type == 'independent' and not prop.unit_ids:
                self.env['lhc.unit'].create({
                    'property_id': prop.id,
                    'code': (prop.code or 'RV') + '-VIL',
                    'unit_type': 'Independent House',
                })
        return records


class LhcUnit(models.Model):
    _name = 'lhc.unit'
    _description = 'LHC Unit'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'code'

    name = fields.Char('Name', compute='_compute_name', store=True)
    code = fields.Char('Unit Code', required=True, tracking=True)
    active = fields.Boolean(default=True)
    property_id = fields.Many2one('lhc.property', string='Property', required=True,
                                  ondelete='restrict', tracking=True)
    unit_type = fields.Char('Type', help="e.g. 1 BHK, Commercial")
    area_sqft = fields.Float('Area (sqft)')
    own_eb_no = fields.Char("Unit's Own EB Service No.")

    # Premises details for the printed agreement (spec 5.9)
    door_no = fields.Char('Plot / Door Number')
    boundaries = fields.Text('Boundaries')
    super_builtup_area = fields.Float('Super Built-up Area (sqft)')

    status = fields.Selection([
        ('vacant', 'Vacant'),
        ('booked', 'Booked'),
        ('occupied', 'Occupied'),
        ('notice', 'Notice Given'),
    ], string='Status', default='vacant', required=True, tracking=True)

    # agreement_ids / current_agreement_id / current_tenant_id are NOT declared
    # here. They point at lhc.agreement and lhc.tenant, which live downstream in
    # lhc_nest_leasing — declaring them here would make properties depend on
    # leasing while leasing already depends on properties. lhc_nest_leasing adds
    # them back onto this same model (and the same columns) via _inherit.
    fixture_ids = fields.One2many('lhc.fixture.purchase', 'unit_id', string='Fixtures')

    # Scoped to the company: two companies may each legitimately have an
    # "A-101", and a global unique(code) would let whichever registered it
    # first block the other — a cross-company leak of the worst kind, because
    # it is visible through an error message rather than through the data.
    _sql_constraints = [
        ('code_uniq', 'unique(code, company_id)',
         'Unit code must be unique within a company.'),
    ]

    @api.depends('code', 'property_id.name')
    def _compute_name(self):
        for unit in self:
            unit.name = "%s — %s" % (unit.code or '', unit.property_id.name or '')
