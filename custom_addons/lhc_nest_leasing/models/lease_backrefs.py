# -*- coding: utf-8 -*-
"""Lease-derived state on the property and tenant masters.

These fields used to be declared alongside the models they sit on, which made
`lhc.unit` reference `lhc.agreement` and `lhc.tenant` reference both — while
`lhc.agreement` already references `lhc.unit` and `lhc.tenant`. Three mutual
cycles, so no addon order could satisfy them.

Declaring them here instead is the standard Odoo direction of travel: the
downstream module extends the upstream model, exactly as `sale` adds fields to
`res.partner` rather than `base` knowing about orders.

Nothing about the database changes. Same models, same columns, same stored
values, same compute logic — only the declaring module moves, so no data is
migrated and no recompute is forced.
"""
from odoo import api, fields, models


class LhcUnit(models.Model):
    _inherit = 'lhc.unit'

    agreement_ids = fields.One2many('lhc.agreement', 'unit_id', string='Agreements')
    current_agreement_id = fields.Many2one('lhc.agreement', string='Current Agreement',
                                           compute='_compute_current', store=True)
    current_tenant_id = fields.Many2one('lhc.tenant', string='Current Tenant',
                                        compute='_compute_current', store=True)

    @api.depends('agreement_ids.state', 'agreement_ids.primary_tenant_id')
    def _compute_current(self):
        for unit in self:
            agr = unit.agreement_ids.filtered(
                lambda a: a.state in ('active', 'notice'))[:1]
            unit.current_agreement_id = agr.id if agr else False
            unit.current_tenant_id = agr.primary_tenant_id.id if agr else False


class LhcTenant(models.Model):
    _inherit = 'lhc.tenant'

    agreement_ids = fields.One2many('lhc.agreement', 'primary_tenant_id', string='Agreements')
    current_unit_id = fields.Many2one('lhc.unit', string='Current Unit',
                                      compute='_compute_current', store=True)
    status = fields.Selection([
        ('active', 'Active'),
        ('notice', 'Notice Given'),
        ('vacated', 'Vacated'),
    ], string='Status', compute='_compute_current', store=True, default='active', index=True)

    @api.depends('agreement_ids.state', 'agreement_ids.unit_id')
    def _compute_current(self):
        for tenant in self:
            agr = tenant.agreement_ids.filtered(
                lambda a: a.state in ('active', 'notice'))[:1]
            tenant.current_unit_id = agr.unit_id.id if agr else False
            if not agr:
                tenant.status = 'vacated' if tenant.agreement_ids else 'active'
            elif agr.state == 'notice':
                tenant.status = 'notice'
            else:
                tenant.status = 'active'
