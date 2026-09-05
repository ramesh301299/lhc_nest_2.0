# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    lhc_gst_rate = fields.Float(
        'GST Rate (%)', config_parameter='lhc_nest.gst_rate', default=18.0,
        help="Single source of truth GST rate used by calculate_billing().")
    lhc_reminder_day = fields.Integer(
        'Reminder Anchor Day', config_parameter='lhc_nest.reminder_day', default=5,
        help="Day of month rent reminders anchor on (spec 4.4).")
