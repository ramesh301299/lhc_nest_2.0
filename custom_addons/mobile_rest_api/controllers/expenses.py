# -*- coding: utf-8 -*-
"""Mobile maintenance / expenses — list, create, detail.

* ``GET  /api/mobile/expenses?scope=<all|unit|building>`` — the Log Expense list
  with a summary (spent this month, recoverable from tenants) and scope counts.
* ``POST /api/mobile/expenses`` — record a new expense. A building-level entry
  with ``split_equally`` fans out one tenant charge per unit (handled by the
  model's create hook).
* ``GET  /api/mobile/expenses/<id>`` — one expense's detail.

Runs as the real Odoo user (``@mobile_endpoint``).
"""
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

_PAYABLE_LABELS = {'owner': 'Owner', 'tenant': 'Tenant'}
_RECOVERY_LABELS = {'na': '', 'pending': 'Pending Recovery', 'recovered': 'Recovered'}
_SCOPE_LABELS = {'unit': 'Unit-specific', 'building': 'Building-level'}


def _expense_json(m):
    return {
        'id': m.id,
        'name': m.name or '',
        'date': m.date.strftime('%d %b %Y') if m.date else '',
        'scope': m.scope or '',
        'scope_label': _SCOPE_LABELS.get(m.scope, m.scope or ''),
        'property': m.property_id.name or '',
        'unit': m.unit_id.code or '' if m.unit_id else '',
        'expense_type': m.expense_type or '',
        'vendor': m.vendor or '',
        'amount': m.amount or 0.0,
        'payable_by': m.payable_by or '',
        'payable_by_label': _PAYABLE_LABELS.get(m.payable_by, m.payable_by or ''),
        'recovery_status': m.recovery_status or '',
        'recovery_label': _RECOVERY_LABELS.get(m.recovery_status, ''),
        'note': m.note or '',
        'is_split': bool(m.is_split),
        'entity': m.posted_entity_id.name or '' if m.posted_entity_id else '',
    }


class MobileExpenses(http.Controller):

    @http.route(f'{API_ROOT}/expenses', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def expenses(self, **kwargs):
        scope = (query_params().get('scope') or 'all').strip().lower()
        Maint = request.env['lhc.maintenance']

        all_records = Maint.search([], order='date desc, id desc')

        domain_records = all_records
        if scope in ('unit', 'building'):
            domain_records = all_records.filtered(lambda m: m.scope == scope)

        # Spent this month — exclude split children so a building expense split
        # across units is not counted twice (parent + shares).
        today = fields.Date.today()
        month_start = today.replace(day=1)
        spent = sum(
            m.amount or 0.0 for m in all_records
            if not m.is_split and m.date and m.date >= month_start
        )
        # Recoverable — tenant-payable charges still pending recovery.
        recoverable = sum(
            m.amount or 0.0 for m in all_records
            if m.payable_by == 'tenant' and m.recovery_status == 'pending'
        )

        return api_success(
            data={
                'summary': {
                    'spent': spent,
                    'recoverable': recoverable,
                },
                'counts': {
                    'all': len(all_records),
                    'unit': len(all_records.filtered(lambda m: m.scope == 'unit')),
                    'building': len(all_records.filtered(lambda m: m.scope == 'building')),
                },
                'scope': scope,
                'expenses': [_expense_json(m) for m in domain_records],
            },
            message='Expenses loaded.',
        )

    @http.route(f'{API_ROOT}/expenses/<int:expense_id>', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def expense_detail(self, expense_id, **kwargs):
        m = request.env['lhc.maintenance'].browse(expense_id)
        if not m.exists():
            return api_error('Expense not found.', status=404)
        return api_success(data=_expense_json(m), message='Expense loaded.')

    @http.route(f'{API_ROOT}/expenses', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def create_expense(self, **kwargs):
        payload = request_payload()

        errors = missing_fields(
            {'property_id': payload.get('property_id'),
             'expense_type': payload.get('expense_type'),
             'amount': payload.get('amount')},
            ['property_id', 'expense_type', 'amount'])
        if errors:
            return validation_error(errors, 'Property, expense type and amount are required.')

        scope = (payload.get('scope') or 'unit').strip().lower()
        if scope not in ('unit', 'building'):
            scope = 'unit'

        try:
            property_id = int(payload.get('property_id'))
        except (TypeError, ValueError):
            return validation_error(
                [{'field': 'property_id', 'message': 'A valid property is required.'}])
        prop = request.env['lhc.property'].browse(property_id)
        if not prop.exists():
            return api_error('Property not found.', status=404)

        try:
            amount = float(payload.get('amount'))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return validation_error(
                [{'field': 'amount', 'message': 'Enter an amount greater than zero.'}])

        vals = {
            'scope': scope,
            'property_id': prop.id,
            'expense_type': (payload.get('expense_type') or '').strip(),
            'vendor': (payload.get('vendor') or '').strip(),
            'amount': amount,
            'payable_by': 'tenant' if payload.get('payable_by') == 'tenant' else 'owner',
            'date': (payload.get('date') or '').strip()
                    or fields.Date.to_string(fields.Date.today()),
            'note': (payload.get('note') or '').strip(),
        }

        if scope == 'unit':
            unit_id = payload.get('unit_id')
            if unit_id:
                unit = request.env['lhc.unit'].browse(int(unit_id))
                if not unit.exists() or unit.property_id.id != prop.id:
                    return api_error('Unit does not belong to that property.', status=422)
                vals['unit_id'] = unit.id
        else:  # building
            vals['split_equally'] = bool(payload.get('split_equally'))

        record = request.env['lhc.maintenance'].create(vals)
        return api_success(data=_expense_json(record), message='Expense logged.')
