# -*- coding: utf-8 -*-
from odoo import fields, models


class LhcAgreementTemplate(models.Model):
    _name = 'lhc.agreement.template'
    _description = 'LHC Agreement Template'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'name'

    name = fields.Char('Template Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    applies_to = fields.Selection([
        ('residential', 'Residential units'),
        ('commercial', 'Commercial / office units'),
        ('villa', 'Independent houses / villas'),
    ], string='Applies To', default='residential', required=True)
    is_default = fields.Boolean('Default')
    default_breach_text = fields.Char(
        'Default / Breach Handling',
        default='12% penal interest, evict after 3 months default',
        help="Pulled read-only into the agreement Dates card.")
    clause_ids = fields.One2many('lhc.agreement.template.clause', 'template_id',
                                 string='Clause Sections')
    clause_count = fields.Integer('Sections', compute='_compute_clause_count')

    def _compute_clause_count(self):
        for tmpl in self:
            tmpl.clause_count = len(tmpl.clause_ids)


class LhcAgreementTemplateClause(models.Model):
    _name = 'lhc.agreement.template.clause'
    _description = 'LHC Agreement Template Clause'
    _order = 'sequence, id'

    template_id = fields.Many2one('lhc.agreement.template', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='template_id.company_id', store=True,
                                 index=True, readonly=True)
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Section Title', required=True)
    body = fields.Text('Clause Text',
                       help="Placeholder structure only — real legal wording must be "
                            "supplied by the owner / lawyer before go-live (spec 5.7).")
