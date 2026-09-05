# -*- coding: utf-8 -*-
"""Mobile home dashboard — ``GET /api/mobile/dashboard``.

The figures are the *same* ones the web dashboard shows. Rather than
recomputing them (which would let the two dashboards silently drift apart), this
endpoint calls ``lhc_nest``'s own ``/lhc/data/dashboard`` handler and reshapes
its result for the app. That handler is the single source of truth for
occupancy, rent due/received/pending, entity-wise collection and the overdue
list; if its rules change, the mobile app follows automatically.

Three lists the web endpoint only returns as *counts* are expanded here, because
the mobile home screen renders them as rows: the receipts awaiting approval, the
tenants needing attention and the agreements expiring soon.

Everything runs as the real Odoo user (``@mobile_endpoint`` switches the request
into their environment), so record rules and the Admin-only visibility of
billing entities apply exactly as they do on the web.
"""
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

# Reuse, don't reimplement: the web dashboard handler is the one place the
# figures are defined. `@http.route` wraps it, but for a `type='json'` route the
# wrapper simply returns the handler's dict, so a direct call gives the same
# result the web client receives.
from odoo.addons.lhc_nest.controllers.main import LhcApp

from .base_controller import API_ROOT, api_success, mobile_endpoint

#: Same window the web dashboard uses for "expiring soon".
EXPIRY_WINDOW_DAYS = 30
#: Active agreement states, matching the web dashboard's definition of "active".
ACTIVE_AGR_STATES = ('active', 'notice')


class MobileDashboard(http.Controller):

    @http.route(f'{API_ROOT}/dashboard', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def dashboard(self, **kwargs):
        # The web handler computes every headline figure as the current user.
        web = LhcApp().lhc_dashboard()

        data = {
            'period': web.get('period'),
            'cards': web.get('cards', {}),
            'entities': web.get('entities', []),
            # The web endpoint already returns the overdue list; the app shows
            # it as "Needs Attention". Kept under both keys so the intent is
            # readable client-side without a second lookup.
            'needs_attention': web.get('overdue_tenants', []),
            'pending_receipts': self._pending_receipts(),
            'expiring_agreements': self._expiring_agreements(),
        }
        return api_success(data=data, message='Dashboard loaded.')

    # ------------------------------------------------------------------
    # Detail lists the web endpoint only exposes as counts
    # ------------------------------------------------------------------
    @staticmethod
    def _pending_receipts():
        """Receipts awaiting approval — the app's "Awaiting Your Approval" card.

        Searched as the caller, so a user who cannot see a receipt never
        receives it. `payment_mode` carries both the stored value and its label
        so the app can show "UPI"/"NEFT/IMPS" without duplicating the mapping.
        """
        Receipt = request.env['lhc.receipt']
        mode_labels = dict(Receipt._fields['payment_mode'].selection)
        receipts = Receipt.search(
            [('state', '=', 'pending')], order='receipt_date desc, id desc')
        rows = []
        for r in receipts:
            rows.append({
                'receipt_id': r.id,
                'name': r.name,
                'tenant': r.tenant_id.name or '',
                'unit': r.unit_id.code or '',
                'amount': r.rent_amount,
                'payment_mode': r.payment_mode or '',
                'payment_mode_label': mode_labels.get(r.payment_mode, ''),
                'posted_by': r.posted_by.name or '',
            })
        return rows

    @staticmethod
    def _expiring_agreements():
        """Active agreements ending within the next 30 days, soonest first."""
        today = fields.Date.today()
        horizon = today + timedelta(days=EXPIRY_WINDOW_DAYS)

        agreements = request.env['lhc.agreement'].search([
            ('state', 'in', ACTIVE_AGR_STATES),
            ('end_date', '>=', today),
            ('end_date', '<=', horizon),
        ])
        rows = []
        for a in agreements:
            rows.append({
                'agreement_id': a.id,
                'tenant': a.primary_tenant_id.name or '',
                'unit': a.unit_id.code or '',
                'end_date': a.end_date.strftime('%d %b %Y') if a.end_date else '',
                'days_left': (a.end_date - today).days if a.end_date else None,
            })
        rows.sort(key=lambda r: (r['days_left'] is None, r['days_left']))
        return rows
