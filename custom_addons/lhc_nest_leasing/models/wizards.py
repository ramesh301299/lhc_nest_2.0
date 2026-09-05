# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import ValidationError


class LhcRenewWizard(models.TransientModel):
    _name = 'lhc.renew.wizard'
    _description = 'LHC Renew Agreement Wizard'

    agreement_id = fields.Many2one('lhc.agreement', required=True)
    current_payable = fields.Float('Current Payable Rent', readonly=True)
    method = fields.Selection([
        ('A', 'A — Escalate current payable by %'),
        ('B', 'B — New base rent + discount'),
        ('C', 'C — Add fixed rupee amount'),
        ('D', 'D — Manual override'),
    ], string='Escalation Method', default='A', required=True)
    pct = fields.Float('Percentage Increase (%)')
    base_rent = fields.Float('New Base Rent (₹)')
    discount = fields.Float('New Discount (₹)')
    service_charge = fields.Float('Service Charge (₹)')
    fixed_amount = fields.Float('Fixed Increase (₹)')
    reason = fields.Text('Justification Note')

    def action_apply(self):
        self.ensure_one()
        if self.method == 'D' and not self.reason:
            raise ValidationError("Manual override (Method D) requires a justification note.")
        self.agreement_id.action_renew(
            method=self.method,
            base_rent=self.base_rent,
            discount=self.discount,
            service_charge=self.service_charge,
            pct=self.pct,
            fixed_amount=self.fixed_amount,
            reason=self.reason,
        )
        return {'type': 'ir.actions.act_window_close'}


class LhcNoticeWizard(models.TransientModel):
    _name = 'lhc.notice.wizard'
    _description = 'LHC Give Notice Wizard'

    agreement_id = fields.Many2one('lhc.agreement', required=True)
    notice_date = fields.Date('Notice Date', default=fields.Date.context_today, required=True)
    notice_period_days = fields.Integer('Notice Period (days)', readonly=True)
    reason = fields.Char('Reason (optional)')

    def action_apply(self):
        self.ensure_one()
        self.agreement_id.action_give_notice(
            notice_date=self.notice_date, reason=self.reason)
        return {'type': 'ir.actions.act_window_close'}
