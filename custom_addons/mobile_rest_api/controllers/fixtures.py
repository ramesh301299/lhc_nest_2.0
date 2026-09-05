# -*- coding: utf-8 -*-
"""Mobile fixtures — ``GET /api/mobile/fixtures``.

The fixture register: what was bought for a unit, what it cost, and whether the
vendor gave a GST bill (which is what makes it input GST credit, spec 5.4). The
same records drive the Agreement → Fixtures tab and the Vacate Checklist, so the
app showing a move-out checklist had no way to look up the item it was
deducting against.

Query params (optional):
  * ``unit_id`` — only this unit's fixtures.
  * ``status`` — ``assigned``, ``unassigned``, or ``all`` (default).

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint, query_params

_CONDITION_LABELS = {'new': 'New', 'good': 'Good', 'fair': 'Fair'}
_STATUS_LABELS = {'assigned': 'Assigned', 'unassigned': 'Awaiting Assignment'}


class MobileFixtures(http.Controller):

    @http.route(f'{API_ROOT}/fixtures', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def fixtures(self, **kwargs):
        params = query_params()
        domain = []

        unit_id = params.get('unit_id')
        if unit_id:
            try:
                domain.append(('unit_id', '=', int(unit_id)))
            except (TypeError, ValueError):
                pass  # An unparseable filter is ignored, not an error.

        status = (params.get('status') or 'all').strip().lower()
        if status in _STATUS_LABELS:
            domain.append(('status', '=', status))

        records = request.env['lhc.fixture.purchase'].search(
            domain, order='purchase_date desc, id desc')

        rows = []
        cost_total = 0.0
        input_credit = 0.0
        for f in records:
            cost_total += f.cost_before_gst or 0.0
            if f.gst_bill:
                input_credit += f.gst_amount or 0.0
            unit = f.unit_id
            rows.append({
                'id': f.id,
                'name': f.name or '',
                'quantity': f.quantity or 0,
                'unit': unit.code or '' if unit else '',
                'unit_id': unit.id or None,
                'property': f.property_id.name or '' if f.property_id else '',
                'vendor': f.vendor or '',
                'purchase_date': f.purchase_date.strftime('%d %b %Y')
                                 if f.purchase_date else '',
                'cost_before_gst': f.cost_before_gst or 0.0,
                'gst_bill': bool(f.gst_bill),
                # Entered from the vendor's bill, never recomputed — rates vary
                # by HSN, so this is the figure the credit is claimed on.
                'gst_amount': f.gst_amount or 0.0,
                'total_cost': (f.cost_before_gst or 0.0) + (f.gst_amount or 0.0),
                'move_in_condition': f.move_in_condition or '',
                'move_in_condition_label':
                    _CONDITION_LABELS.get(f.move_in_condition, ''),
                'status': f.status or '',
                'status_label': _STATUS_LABELS.get(f.status, f.status or ''),
                # The bill itself is a binary; the app only needs to know one
                # exists, so it can prompt to view it on the web.
                'has_bill_file': bool(f.bill_file),
                'bill_filename': f.bill_filename or '',
            })

        return api_success(
            data={
                'summary': {
                    'count': len(rows),
                    'cost_total': cost_total,
                    'input_gst_credit': input_credit,
                },
                'fixtures': rows,
            },
            message='Fixtures loaded.',
        )
