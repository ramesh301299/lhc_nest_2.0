# -*- coding: utf-8 -*-
"""Mobile tenants list — ``GET /api/mobile/tenants``.

The roster behind the app's Tenants tab. Mirrors the web tenants list
(``/lhc/data/tenants``) — the same search columns and status filter — but adds
the two things the mobile row needs that the web list omits: the property name
(shown under the tenant) and the current agreement id (so a tapped row can open
that agreement's detail screen).

Query params (all optional):
  * ``search`` — matches name, phone, company, unit code or agreement number.
  * ``status`` — ``active`` (default), ``notice``, ``vacated`` or ``archived``;
    ``all`` returns every non-archived tenant.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint, query_params

#: Tenant states the app can ask for, besides the "all"/"archived" specials.
_STATUS_FILTERS = ('active', 'notice', 'vacated')
#: Active-agreement states, matching the web list's "current agreement" pick.
_ACTIVE_AGR_STATES = ('active', 'notice')


class MobileTenants(http.Controller):

    @http.route(f'{API_ROOT}/tenants', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def tenants(self, **kwargs):
        params = query_params()
        search = (params.get('search') or '').strip()
        status = (params.get('status') or 'active').strip().lower()

        Tenant = request.env['lhc.tenant']
        domain = []
        if search:
            domain += ['|', '|', '|', '|',
                       ('name', 'ilike', search),
                       ('mobile', 'ilike', search),
                       ('company_name', 'ilike', search),
                       ('current_unit_id.code', 'ilike', search),
                       ('agreement_ids.name', 'ilike', search)]

        if status == 'archived':
            Tenant = Tenant.with_context(active_test=False)
            domain.append(('active', '=', False))
        elif status in _STATUS_FILTERS:
            domain.append(('status', '=', status))
        # status == 'all' (or anything else) → no status clause, current tenants.

        rows = []
        for t in Tenant.search(domain, order='name'):
            agr = t.agreement_ids.filtered(
                lambda a: a.state in _ACTIVE_AGR_STATES)[:1]
            unit = t.current_unit_id or (agr.unit_id if agr else t.current_unit_id)
            rows.append({
                'id': t.id,
                'name': t.name or '',
                'phone': t.mobile or '',
                'unit': unit.code or '' if unit else '',
                'property': unit.property_id.name or '' if unit and unit.property_id else '',
                'agreement': agr.name or '' if agr else '',
                # The tap target: null when the tenant has no current agreement,
                # so the app leaves that row non-navigable rather than opening a
                # detail screen for an agreement that does not exist.
                'agreement_id': agr.id if agr else None,
                'status': t.status or 'active',
                'is_company': t.tenant_type == 'company',
                'gst': bool(t.gstin),
            })

        return api_success(
            data={'tenants': rows, 'total': len(rows)},
            message='Tenants loaded.',
        )
