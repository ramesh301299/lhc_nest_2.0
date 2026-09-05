# -*- coding: utf-8 -*-
"""Mobile dues list — ``GET /api/mobile/dues``.

The "Check Dues" screen needs one thing the dashboard's overdue list does not:
the split between a tenant who has paid *nothing* this month (fully overdue) and
one who has paid *part* of it (a balance still pending). That split needs the
amount received per agreement, so it is computed here rather than reused from the
dashboard handler.

The month window and the "active" definition match the dashboard exactly
(``lhc_nest``'s ``/lhc/data/dashboard``): rent is due for every agreement in the
``active``/``notice`` state, and what counts as received is the sum of *approved*
receipts dated within the current month. A tenant appears here only while their
paid amount is short of the rent payable.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply exactly
as they do on the web.
"""
from odoo import fields, http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint

#: Matches the dashboard's definition of an active, rent-bearing agreement.
ACTIVE_AGR_STATES = ('active', 'notice')
#: A shortfall smaller than this is floating-point noise, not a real balance.
_EPSILON = 0.01


class MobileDues(http.Controller):

    @http.route(f'{API_ROOT}/dues', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def dues(self, **kwargs):
        env = request.env
        today = fields.Date.today()
        month_start = today.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        active_agr = env['lhc.agreement'].search(
            [('state', 'in', ACTIVE_AGR_STATES)])

        # Approved receipts this month, summed per agreement — the same source
        # the dashboard uses for "received".
        month_receipts = env['lhc.receipt'].search([
            ('state', '=', 'approved'),
            ('receipt_date', '>=', month_start),
            ('receipt_date', '<', next_month),
        ])
        received_by_agr = {}
        for rec in month_receipts:
            received_by_agr[rec.agreement_id.id] = \
                received_by_agr.get(rec.agreement_id.id, 0.0) + rec.rent_amount

        dues = []
        total_overdue = 0.0
        partial_amount = 0.0
        partial_count = 0
        for a in active_agr:
            payable = a.payable_rent or 0.0
            received = received_by_agr.get(a.id, 0.0)
            shortfall = payable - received
            if shortfall <= _EPSILON:
                continue

            # Paid something but not everything → a balance is pending;
            # paid nothing at all → fully overdue.
            partial = received > _EPSILON
            due_day = min(a.due_day or 5, 28)
            due_since = month_start.replace(day=due_day)

            dues.append({
                'agreement_id': a.id,
                'tenant': a.primary_tenant_id.name or '',
                'phone': a.primary_tenant_id.mobile or '',
                'unit': a.unit_id.code or '',
                'due_date': due_since.strftime('%d %b'),
                'amount': shortfall,
                'partial': partial,
                'tag': 'Balance' if partial else 'Overdue',
                'note': 'Partial paid' if partial else 'Not paid',
            })
            total_overdue += shortfall
            if partial:
                partial_amount += shortfall
                partial_count += 1

        # Biggest balance first — the tenant to chase soonest sits at the top.
        dues.sort(key=lambda d: d['amount'], reverse=True)

        return api_success(
            data={
                'period': today.strftime('%B %Y'),
                'summary': {
                    'total_overdue': total_overdue,
                    'overdue_tenants': len(dues),
                    'partial_amount': partial_amount,
                    'partial_tenants': partial_count,
                },
                'dues': dues,
            },
            message='Dues loaded.',
        )
