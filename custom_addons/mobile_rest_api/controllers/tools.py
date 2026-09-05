# -*- coding: utf-8 -*-
"""Mobile tools — billing entities and WhatsApp message templates.

* ``GET /api/mobile/entities`` — the billing entities (lessors) with their GST
  flag and bank label. ``/withdrawals`` already returned a bare id/name list for
  its dropdown; this is the full record the Settings and Agreement screens need,
  and it is the one place GST applicability is decided (spec 5.12).
* ``GET /api/mobile/wa-templates`` — the copy-paste message templates. Phase 1
  is copy-paste only: nothing here sends anything, it hands the app the text.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint, query_params

_TEMPLATE_LABELS = {
    'reminder': 'Payment Reminder',
    'renewal': 'Renewal Reminder',
    'receipt': 'Receipt Confirmation',
    'other': 'Other',
}


class MobileTools(http.Controller):

    @http.route(f'{API_ROOT}/entities', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def entities(self, **kwargs):
        records = request.env['lhc.billing.entity'].search([], order='name')

        rows = [{
            'id': e.id,
            'name': e.name or '',
            'gst_applicable': bool(e.gst_applicable),
            'gstin': e.gstin or '',
            # 'GST Tax Invoice' or 'Non-GST Rent Receipt' — the document this
            # entity issues, computed on the model so the app does not decide it.
            'receipt_type': e.receipt_type or '',
            'mobile': e.mobile or '',
            'pan': e.pan or '',
            'bank_label': e.bank_label or '',
            'bank_name': e.bank_name or '',
            'bank_branch': e.bank_branch or '',
            'bank_ifsc': e.bank_ifsc or '',
            # The account number is deliberately absent: the masked label is
            # enough to pick an account on a phone, and the full number is not.
            'receives_building_expenses': bool(e.also_receives_building),
        } for e in records]

        return api_success(
            data={
                'summary': {
                    'count': len(rows),
                    'gst_entities': sum(1 for r in rows if r['gst_applicable']),
                },
                'entities': rows,
            },
            message='Entities loaded.',
        )

    @http.route(f'{API_ROOT}/wa-templates', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def wa_templates(self, **kwargs):
        template_type = (query_params().get('type') or '').strip().lower()
        domain = [('template_type', '=', template_type)] \
            if template_type in _TEMPLATE_LABELS else []

        records = request.env['lhc.wa.template'].search(domain, order='name')

        rows = [{
            'id': t.id,
            'name': t.name or '',
            'template_type': t.template_type or '',
            'template_type_label': _TEMPLATE_LABELS.get(
                t.template_type, t.template_type or ''),
            'body': t.body or '',
        } for t in records]

        return api_success(
            data={'templates': rows, 'total': len(rows)},
            message='Templates loaded.',
        )
