# -*- coding: utf-8 -*-
"""Mobile unit bookings — ``GET /api/mobile/bookings``.

A token advance taken on a vacant unit before an agreement exists (spec 4.3).
The web app has this screen; the app did not, so a unit could show as "Booked"
in ``/properties`` with nothing anywhere to say who booked it, for how much, or
when. This is that missing half.

Query params (optional):
  * ``state`` — ``booked`` (default), ``converted``, ``cancelled`` or ``all``.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint, query_params

_STATES = ('booked', 'converted', 'cancelled')
_STATE_LABELS = {'booked': 'Booked', 'converted': 'Converted',
                 'cancelled': 'Cancelled'}
_MODE_LABELS = {'cash': 'Cash', 'upi': 'UPI', 'neft': 'NEFT/IMPS',
                'cheque': 'Cheque'}


class MobileBookings(http.Controller):

    @http.route(f'{API_ROOT}/bookings', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def bookings(self, **kwargs):
        state = (query_params().get('state') or 'booked').strip().lower()
        domain = [] if state == 'all' else [('state', '=', state if state in _STATES else 'booked')]

        records = request.env['lhc.booking'].search(
            domain, order='date_received desc, id desc')

        rows = []
        token_total = 0.0
        for b in records:
            unit = b.unit_id
            token_total += b.token_amount or 0.0
            rows.append({
                'id': b.id,
                'name': b.name or '',
                'prospect_name': b.prospect_name or '',
                'phone': b.phone or '',
                'unit': unit.code or '',
                'unit_id': unit.id or None,
                'property': unit.property_id.name or '' if unit.property_id else '',
                'unit_status': unit.status or '',
                'token_amount': b.token_amount or 0.0,
                'date_received': b.date_received.strftime('%d %b %Y')
                                 if b.date_received else '',
                'mode': b.mode or '',
                'mode_label': _MODE_LABELS.get(b.mode, b.mode or ''),
                'note': b.note or '',
                'state': b.state or '',
                'state_label': _STATE_LABELS.get(b.state, b.state or ''),
            })

        return api_success(
            data={
                'state': state,
                'summary': {'count': len(rows), 'token_total': token_total},
                'bookings': rows,
            },
            message='Bookings loaded.',
        )
