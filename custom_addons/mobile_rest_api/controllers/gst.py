# -*- coding: utf-8 -*-
"""Mobile GST & statutory screen — ``GET /api/mobile/gst``.

Per-entity GST position, the remittances already paid, and the auditor's fees.
``lhc_nest_reports`` reached the app only as dashboard figures and withdrawals,
so the GST liability an owner actually has to settle was web-only.

The per-entity figures come from ``lhc.gst.summary.entity_summary`` — the same
helper the web report uses — rather than being recomputed here, so the closing
liability shown on the phone cannot drift from the one shown on the web.

Query params (optional):
  * ``entity_id`` — restrict to one billing entity.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply — an
accountant who may not read billing entities simply gets an empty list.
"""
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint, query_params


class MobileGst(http.Controller):

    @http.route(f'{API_ROOT}/gst', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def gst(self, **kwargs):
        env = request.env
        Summary = env['lhc.gst.summary']

        domain = [('gst_applicable', '=', True)]
        raw_entity = query_params().get('entity_id')
        if raw_entity:
            try:
                domain.append(('id', '=', int(raw_entity)))
            except (TypeError, ValueError):
                pass

        entities = env['lhc.billing.entity'].search(domain, order='name')

        rows = []
        totals = {'gst_collected': 0.0, 'input_credit': 0.0, 'remitted': 0.0,
                  'closing_liability': 0.0, 'carry_forward_credit': 0.0}
        for entity in entities:
            figures = Summary.entity_summary(entity)
            rows.append(dict(figures, entity_id=entity.id, name=entity.name or '',
                             gstin=entity.gstin or ''))
            for key in totals:
                totals[key] += figures.get(key, 0.0)

        payments = [{
            'id': p.id,
            'name': p.name or '',
            'entity': p.entity_id.name or '',
            'entity_id': p.entity_id.id or None,
            'period': p.period or '',
            'payment_date': p.payment_date.strftime('%d %b %Y')
                            if p.payment_date else '',
            'amount': p.amount or 0.0,
            'challan': p.challan or '',
            'has_proof': bool(p.proof),
            'entered_by': p.entered_by.name or '',
        } for p in env['lhc.gst.payment'].search([], order='payment_date desc, id desc')]

        fees = [{
            'id': f.id,
            'name': f.name or '',
            'amount': f.amount or 0.0,
            'date': f.date.strftime('%d %b %Y') if f.date else '',
            'note': f.note or '',
        } for f in env['lhc.auditor.fee'].search([], order='date desc, id desc')]

        return api_success(
            data={
                'summary': totals,
                'entities': rows,
                'payments': payments,
                'payments_total': sum(p['amount'] for p in payments),
                'auditor_fees': fees,
                'auditor_fees_total': sum(f['amount'] for f in fees),
            },
            message='GST summary loaded.',
        )
