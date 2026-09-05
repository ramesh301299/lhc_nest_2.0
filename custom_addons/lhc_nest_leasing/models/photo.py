# -*- coding: utf-8 -*-
from odoo import fields, models


class LhcUnitPhoto(models.Model):
    """One shared photos table backing web comparison + mobile capture (spec 5.10)."""
    _name = 'lhc.unit.photo'
    _description = 'LHC Move-in / Move-out Photo'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'event_type, room_label'

    unit_id = fields.Many2one('lhc.unit', string='Unit', required=True, ondelete='cascade')
    agreement_id = fields.Many2one('lhc.agreement', string='Agreement')
    event_type = fields.Selection([
        ('move_in', 'Move-in'),
        ('move_out', 'Move-out'),
    ], string='Event', required=True, default='move_in', tracking=True)
    room_label = fields.Char('Room / Area', required=True)
    uploaded_date = fields.Date('Date', default=fields.Date.context_today)
    image = fields.Binary('Photo')
    image_filename = fields.Char('Filename')
    damage_noted = fields.Boolean('Damage Noted?', tracking=True)
    note = fields.Char('Note')
