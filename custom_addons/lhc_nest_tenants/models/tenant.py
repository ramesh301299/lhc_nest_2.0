# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LhcTenant(models.Model):
    _name = 'lhc.tenant'
    _description = 'LHC Tenant'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'name'

    name = fields.Char('Full Name', required=True, tracking=True, index=True)
    active = fields.Boolean(default=True)
    tenant_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company / GST'),
    ], string='Tenant Type', default='individual', required=True)

    # Individual fields (spec 5.9)
    relation = fields.Char('Relation (S/o or W/o + name)')
    age = fields.Integer('Age')
    aadhaar = fields.Char('Aadhaar No.')
    pan = fields.Char('PAN')
    mobile = fields.Char('Phone', index=True)
    email = fields.Char('Email')
    present_address = fields.Text('Present Address')
    permanent_address = fields.Text('Permanent Address (if different)')
    photo_id_doc = fields.Binary('Photo ID Upload')
    photo_id_filename = fields.Char('Photo ID Filename')
    move_in_date = fields.Date('Move-in Date')

    # Company / GST fields
    company_name = fields.Char('Company Name')
    gstin = fields.Char('GSTIN')
    # Authorized representative sub-record
    rep_name = fields.Char('Representative Name')
    rep_relation = fields.Char('Representative Relation')
    rep_pan = fields.Char('Representative PAN')
    rep_aadhaar = fields.Char('Representative Aadhaar')
    rep_mobile = fields.Char('Representative Mobile')
    rep_address = fields.Text('Representative Address')

    # agreement_ids / current_unit_id / status are NOT declared here. A tenant's
    # occupancy and status are functions of their agreements, which live
    # downstream in lhc_nest_leasing. Declaring them here would make the tenant
    # master depend on leasing. lhc_nest_leasing adds them back onto this same
    # model, and the same columns, via _inherit.
