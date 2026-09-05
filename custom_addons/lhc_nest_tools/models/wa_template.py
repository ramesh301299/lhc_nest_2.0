# -*- coding: utf-8 -*-
from odoo import fields, models


class LhcWaTemplate(models.Model):
    """WhatsApp copy-paste templates. Phase 1 is copy-paste only — no WhatsApp/
    SMS/email integration anywhere in the system (spec 5.6)."""
    _name = 'lhc.wa.template'
    _description = 'LHC WhatsApp Template'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'name'

    name = fields.Char('Template Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    template_type = fields.Selection([
        ('reminder', 'Payment Reminder'),
        ('renewal', 'Renewal Reminder'),
        ('receipt', 'Receipt Confirmation'),
        ('other', 'Other'),
    ], string='Type', default='reminder')
    body = fields.Text('Message Body',
                       help="Use placeholders like {tenant}, {unit}, {amount}, {due_date}. "
                            "Copy-paste into WhatsApp — the system never sends automatically.")
