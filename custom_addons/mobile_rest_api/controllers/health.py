# -*- coding: utf-8 -*-
"""The module's only endpoint: a readiness probe.

It confirms three things and nothing more — the module is installed, the route
map is serving it, and the ORM answers. It reports no Odoo build number, no
database name, no host and no configuration, because a probe reachable without
authentication should tell an unknown caller only whether the service is up.

The ORM touch is deliberate. Odoo builds the registry and routing map lazily,
on a worker's first request, so after a restart or an idle period the first
call can hit a cold worker. Doing that work here means an uptime monitor
absorbs it, not the app's first real request.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_error, api_success, public_endpoint

MODULE_NAME = 'mobile_rest_api'
#: Compatibility marker for the app. The major version only — the exact build
#: is server information the client has no need for.
ODOO_VERSION = '18'


class MobileRestHealth(http.Controller):

    @http.route(f'{API_ROOT}/health', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @public_endpoint
    def health(self, **kwargs):
        installed = request.env['ir.module.module'].sudo().search_count([
            ('name', '=', MODULE_NAME),
            ('state', '=', 'installed'),
        ])
        if not installed:
            # The route is being served from files on disk while the module is
            # not actually installed in this database — report not-ready rather
            # than claim success.
            return api_error('Mobile REST API is starting.', status=503)

        return api_success(
            data={
                'module': MODULE_NAME,
                'odoo_version': ODOO_VERSION,
            },
            message='Mobile REST API is running.',
        )
