# -*- coding: utf-8 -*-
"""Mobile monthly bills — ``GET /api/mobile/bills``.

The Monthly Bills screen: bills for a billing period, with a summary (billed vs
collected) and the list of documents. Each bill carries the tenant's phone so
the app can share that one bill directly, rather than a single bulk action.

Query params (optional):
  * ``period`` — e.g. "September 2026". Defaults to the most recent period that
    has bills.

Runs as the real Odoo user (``@mobile_endpoint``).
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_error, api_success, mobile_endpoint, query_params

_STATE_LABELS = {
    'awaiting': 'Awaiting',
    'paid': 'Paid',
    'cancelled': 'Cancelled',
}


class MobileBills(http.Controller):

    @http.route(f'{API_ROOT}/bills', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def bills(self, **kwargs):
        Bill = request.env['lhc.bill']

        # Distinct billing periods, newest first (by the latest bill in each).
        periods = []
        for b in Bill.search([], order='create_date desc'):
            if b.period and b.period not in periods:
                periods.append(b.period)

        requested = (query_params().get('period') or '').strip()
        # Honour any requested period, even one with no bills, so the app can
        # show "no records found" for that month instead of silently jumping to
        # the latest month that does have bills. Only fall back when the caller
        # asked for nothing.
        period = requested or (periods[0] if periods else '')

        bills = Bill.search([('period', '=', period)], order='tenant_id, id') \
            if period else Bill.browse()

        rows = []
        billed = 0.0
        collected = 0.0
        paid_count = 0
        for b in bills:
            total = b.total or 0.0
            billed += total
            if b.state == 'paid':
                collected += total
                paid_count += 1
            rows.append({
                'id': b.id,
                'name': b.name or '',
                'tenant': b.tenant_id.name or '',
                'phone': b.tenant_id.mobile or '',
                'unit': b.unit_id.code or '',
                'agreement_id': b.agreement_id.id if b.agreement_id else None,
                'rent': b.rent_amount or 0.0,
                'maintenance': b.maintenance_amount or 0.0,
                'gst': b.gst_amount or 0.0,
                'total': total,
                'gst_applicable': bool(b.gst_applicable),
                'doc_type': b.doc_type or '',
                'state': b.state or '',
                'state_label': _STATE_LABELS.get(b.state, b.state or ''),
            })

        settled_pct = round((collected / billed) * 100) if billed else 0
        return api_success(
            data={
                'periods': periods,
                'period': period,
                'summary': {
                    'billed': billed,
                    'collected': collected,
                    'count': len(rows),
                    'paid_count': paid_count,
                    'awaiting_count': len(rows) - paid_count,
                    'settled_pct': settled_pct,
                },
                'bills': rows,
            },
            message='Bills loaded.',
        )

    @http.route(f'{API_ROOT}/bills/<int:bill_id>', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def bill_detail(self, bill_id, **kwargs):
        b = request.env['lhc.bill'].browse(bill_id)
        if not b.exists():
            return api_error('Bill not found.', status=404)
        unit = b.unit_id
        return api_success(
            data={
                'id': b.id,
                'name': b.name or '',
                'doc_type': b.doc_type or '',
                'tenant': b.tenant_id.name or '',
                'phone': b.tenant_id.mobile or '',
                'unit': unit.code or '',
                'property': unit.property_id.name or '' if unit.property_id else '',
                'agreement_id': b.agreement_id.id if b.agreement_id else None,
                'period': b.period or '',
                'rent': b.rent_amount or 0.0,
                'maintenance': b.maintenance_amount or 0.0,
                'gst': b.gst_amount or 0.0,
                'gst_applicable': bool(b.gst_applicable),
                'total': b.total or 0.0,
                'state': b.state or '',
                'state_label': _STATE_LABELS.get(b.state, b.state or ''),
                'receipt_no': b.receipt_id.name or '' if b.receipt_id else '',
            },
            message='Bill loaded.',
        )
