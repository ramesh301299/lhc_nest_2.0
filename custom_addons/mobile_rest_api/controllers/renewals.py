# -*- coding: utf-8 -*-
"""Mobile renewal reminders — list + renew.

* ``GET  /api/mobile/renewals`` — active agreements expiring soon (the list the
  app's Agreement Renewals screen shows). ``?days=N`` sets the window; default
  30, matching the dashboard's "expiring" alert so the count agrees with this
  list.
* ``POST /api/mobile/agreements/<id>/renew`` — the mobile equivalent of the web
  Renew wizard. Delegates to ``lhc.agreement.action_renew`` (which creates a new
  version and is Admin-only, enforced in the model), so the four escalation
  methods behave exactly as they do on the web.

Both run as the real Odoo user (``@mobile_endpoint``).
"""
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    mobile_endpoint,
    query_params,
    request_payload,
)

_ACTIVE_AGR_STATES = ('active', 'notice')
_DEFAULT_WINDOW_DAYS = 30
#: Escalation methods accepted by the renew action (mirror the web wizard).
_RENEW_METHODS = ('A', 'B', 'C', 'D')


class MobileRenewals(http.Controller):

    @http.route(f'{API_ROOT}/renewals', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def renewals(self, **kwargs):
        params = query_params()
        # `all=1` returns every active/notice agreement (the More-screen view);
        # otherwise the list is bounded to `days` ahead (the dashboard alert).
        show_all = str(params.get('all') or '').lower() in ('1', 'true', 'yes')

        try:
            days = int(params.get('days') or _DEFAULT_WINDOW_DAYS)
        except (TypeError, ValueError):
            days = _DEFAULT_WINDOW_DAYS
        days = max(1, min(365, days))

        today = fields.Date.today()
        domain = [('state', 'in', _ACTIVE_AGR_STATES)]
        if not show_all:
            horizon = today + timedelta(days=days)
            domain += [('end_date', '>=', today), ('end_date', '<=', horizon)]
        agreements = request.env['lhc.agreement'].search(domain)

        rows = [{
            'agreement_id': a.id,
            'unit': a.unit_id.code or '',
            'tenant': a.primary_tenant_id.name or '',
            'property': a.unit_id.property_id.name or '' if a.unit_id.property_id else '',
            'expires': a.end_date.strftime('%d %b %Y') if a.end_date else '',
            'days_left': (a.end_date - today).days if a.end_date else None,
            'payable_rent': a.payable_rent or 0.0,
        } for a in agreements]
        rows.sort(key=lambda r: (r['days_left'] is None, r['days_left']))

        return api_success(
            data={'all': show_all, 'window_days': None if show_all else days,
                  'renewals': rows},
            message='Renewals loaded.',
        )

    @http.route(f'{API_ROOT}/agreements/<int:agreement_id>/renew', type='http',
                auth='public', methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def renew(self, agreement_id, **kwargs):
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Agreement not found.', status=404)

        payload = request_payload()
        method = (payload.get('method') or 'A').strip().upper()
        if method not in _RENEW_METHODS:
            return api_error('Invalid renewal method.', status=422, errors=[
                {'field': 'method', 'message': 'Method must be one of A, B, C, D.'}])

        def num(key):
            v = payload.get(key)
            if v in (None, ''):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        reason = (payload.get('reason') or '').strip()
        if method == 'D' and not reason:
            return api_error(
                'Manual override (Method D) requires a justification note.',
                status=422,
                errors=[{'field': 'reason', 'message': 'A justification note is required.'}])

        # action_renew is Admin-only (raises AccessError otherwise) and creates
        # a NEW version — old versions are preserved, never edited in place.
        # Any UserError/ValidationError it raises is mapped to a 422 by the
        # base controller, with the model's own message passed through.
        agr.action_renew(
            method=method,
            pct=num('pct'),
            base_rent=num('base_rent'),
            discount=num('discount'),
            service_charge=num('service_charge'),
            fixed_amount=num('fixed_amount'),
            reason=reason or None,
        )

        return api_success(
            data={
                'agreement_id': agr.id,
                'payable_rent': agr.payable_rent or 0.0,
                'start_date': agr.start_date.strftime('%d %b %Y') if agr.start_date else '',
                'end_date': agr.end_date.strftime('%d %b %Y') if agr.end_date else '',
            },
            message='Agreement renewed.',
        )
