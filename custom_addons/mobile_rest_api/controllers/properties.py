# -*- coding: utf-8 -*-
"""Mobile properties & units — ``GET /api/mobile/properties``.

Backs the Properties & Units screen: a portfolio summary (properties, occupied,
vacant, occupancy %) followed by one card per property with its units. Mirrors
the web ``/lhc/data/properties`` payload and adds the per-property occupancy
percentage, an overall summary, and per-unit ``agreement_id`` / notice flag the
mobile card renders.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint


class MobileProperties(http.Controller):

    @http.route(f'{API_ROOT}/properties', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def properties(self, **kwargs):
        properties = request.env['lhc.property'].search([], order='name')

        rows = []
        total_units = 0
        total_occupied = 0
        total_vacant = 0
        for p in properties:
            units = []
            for u in p.unit_ids:
                tenant = u.current_tenant_id
                units.append({
                    'id': u.id,
                    'code': u.code or '',
                    'status': u.status,  # vacant / booked / occupied
                    'tenant': tenant.name or '' if tenant else '',
                    # The tenant may be occupying but on notice — the card shows
                    # a distinct "Notice" state, so surface it explicitly.
                    'tenant_on_notice': bool(tenant) and tenant.status == 'notice',
                    'agreement_id': u.current_agreement_id.id
                    if u.current_agreement_id else None,
                    'unit_type': u.unit_type or '',
                })
            unit_count = p.unit_count or 0
            occupied = p.occupied_count or 0
            rows.append({
                'id': p.id,
                'name': p.name or '',
                'code': p.code or '',
                'property_type': p.property_type or '',
                'location': p.location or '',
                'common_eb_no': p.common_eb_no or '',
                'unit_count': unit_count,
                'occupied_count': occupied,
                'vacant_count': p.vacant_count or 0,
                'occupancy_pct': round(occupied / unit_count * 100) if unit_count else 0,
                'units': units,
            })
            total_units += unit_count
            total_occupied += occupied
            total_vacant += p.vacant_count or 0

        return api_success(
            data={
                'summary': {
                    'properties': len(rows),
                    'units': total_units,
                    'occupied': total_occupied,
                    'vacant': total_vacant,
                    'occupancy_pct':
                        round(total_occupied / total_units * 100) if total_units else 0,
                },
                'properties': rows,
            },
            message='Properties loaded.',
        )
