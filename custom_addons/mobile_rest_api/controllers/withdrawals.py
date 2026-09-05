# -*- coding: utf-8 -*-
"""Mobile personal withdrawals — ``GET /api/mobile/withdrawals``.

Owners' personal draws, tracked per name (billing entity). Backs the app's
Personal Withdrawals screen: per-name totals for a financial year plus the
transaction history for that year.

Admin-only on the web ("Not visible to Accountant"); the mobile app already
admits only admins, so no extra gate is added here beyond the standard token.

Query params (optional):
  * ``fy`` — financial year start, e.g. ``2025`` or ``2025-26``. Defaults to the
    Indian financial year (Apr–Mar) that contains today.

Runs as the real Odoo user (``@mobile_endpoint``).
"""
from datetime import date

from odoo import fields, http
from odoo.http import request

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    missing_fields,
    mobile_endpoint,
    query_params,
    request_payload,
    validation_error,
)


def _fy_bounds(fy_param):
    """Return (start_date, end_exclusive_date, label) for the given FY.

    The Indian financial year runs 1 Apr → 31 Mar. ``fy_param`` may be a start
    year ("2025") or a range ("2025-26"); anything unparseable falls back to the
    FY containing today.
    """
    start_year = None
    if fy_param:
        head = str(fy_param).strip().split('-')[0]
        if head.isdigit() and len(head) == 4:
            start_year = int(head)
    if start_year is None:
        today = fields.Date.today()
        start_year = today.year if today.month >= 4 else today.year - 1

    start = date(start_year, 4, 1)
    end = date(start_year + 1, 4, 1)
    label = '%d-%s' % (start_year, str(start_year + 1)[2:])
    return start, end, label


class MobileWithdrawals(http.Controller):

    @http.route(f'{API_ROOT}/withdrawals', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def withdrawals(self, **kwargs):
        params = query_params()
        fy_start, fy_end, fy_label = _fy_bounds(params.get('fy'))

        records = request.env['lhc.withdrawal'].search([
            ('date', '>=', fy_start),
            ('date', '<', fy_end),
        ], order='date desc, id desc')

        # Per-name (billing entity) totals for the year — the summary cards.
        totals = {}
        order = []  # preserve first-seen order for a stable card layout
        transactions = []
        grand_total = 0.0
        for w in records:
            entity = w.entity_id
            key = entity.id
            if key not in totals:
                totals[key] = {'entity_id': key, 'name': entity.name or '', 'total': 0.0}
                order.append(key)
            totals[key]['total'] += w.amount or 0.0
            grand_total += w.amount or 0.0
            transactions.append({
                'id': w.id,
                'name': entity.name or '',
                'entity_id': key,
                'amount': w.amount or 0.0,
                'date': w.date.strftime('%d %b %Y') if w.date else '',
                'note': w.note or '',
                'entered_by': w.entered_by.name or '',
            })

        # Names for the "Record Withdrawal" dropdown — every billing entity,
        # regardless of whether it has withdrawals this year.
        entities = [{'id': e.id, 'name': e.name or ''}
                    for e in request.env['lhc.billing.entity'].search([], order='name')]

        return api_success(
            data={
                'fy': fy_label,
                'grand_total': grand_total,
                'summary': [totals[k] for k in order],
                'transactions': transactions,
                'entities': entities,
            },
            message='Withdrawals loaded.',
        )

    @http.route(f'{API_ROOT}/withdrawals', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def create_withdrawal(self, **kwargs):
        payload = request_payload()

        errors = missing_fields(
            {'entity_id': payload.get('entity_id'), 'amount': payload.get('amount')},
            ['entity_id', 'amount'])
        if errors:
            return validation_error(errors, 'Name and amount are required.')

        try:
            entity_id = int(payload.get('entity_id'))
        except (TypeError, ValueError):
            return validation_error(
                [{'field': 'entity_id', 'message': 'A valid name is required.'}])
        entity = request.env['lhc.billing.entity'].browse(entity_id)
        if not entity.exists():
            return api_error('Name not found.', status=404)

        try:
            amount = float(payload.get('amount'))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return validation_error(
                [{'field': 'amount', 'message': 'Enter an amount greater than zero.'}])

        # Date is optional; default to today, matching the web form's behaviour
        # when left blank. Accepts an ISO 'YYYY-MM-DD' string.
        date = (payload.get('date') or '').strip() or fields.Date.to_string(fields.Date.today())
        note = (payload.get('note') or '').strip()

        # `entered_by` is stamped as the caller (the request already runs as the
        # real user), so the history's "Entered By" is accurate and not spoofable
        # from the client.
        record = request.env['lhc.withdrawal'].create({
            'entity_id': entity.id,
            'amount': amount,
            'date': date,
            'note': note,
            'entered_by': request.env.user.id,
        })

        return api_success(
            data={
                'id': record.id,
                'name': record.entity_id.name or '',
                'amount': record.amount or 0.0,
                'date': record.date.strftime('%d %b %Y') if record.date else '',
                'note': record.note or '',
                'entered_by': record.entered_by.name or '',
            },
            message='Withdrawal recorded.',
        )
