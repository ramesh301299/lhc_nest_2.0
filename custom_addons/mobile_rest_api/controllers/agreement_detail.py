# -*- coding: utf-8 -*-
"""Mobile agreement detail — ``GET /api/mobile/agreements/<id>``.

Backs the detail screen the app opens when a row in a list (dues, agreements,
tenants) is tapped. It gathers, for one agreement, the same facts the web
agreement form shows — tenant, unit, billing/bank, dates & terms, rent and
deposit — plus the derived bits the mobile card needs: this month's payment
status and the tenant's pending, tenant-payable maintenance.

Runs as the real Odoo user (``@mobile_endpoint``): a 404 is returned for an id
the caller may not see, exactly as the web client would refuse it.
"""
from odoo import fields, http
from odoo.http import request

from .base_controller import API_ROOT, api_error, api_success, mobile_endpoint

_EPSILON = 0.01

#: Human labels for the agreement's escalation frequency selection. Kept here
#: rather than read from the field so the wording stays stable for the app even
#: if the backend relabels the selection.
_ESCALATION_FREQ = {
    '1': '1st Renewal (every term)',
    '2': '2nd Renewal (skip one)',
    '3': '3rd Renewal (skip two)',
}


class MobileAgreementDetail(http.Controller):

    #: Human labels for the ledger entry types.
    _LEDGER_TYPES = {
        'due': 'Rent Due',
        'receipt': 'Receipt',
        'tds': 'TDS Credited',
        'adjust': 'Adjustment',
    }

    @http.route(f'{API_ROOT}/agreements/<int:agreement_id>/ledger', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def ledger(self, agreement_id, **kwargs):
        """The tenant's ledger for this agreement — charges (debit) and payments
        (credit) in date order, with a running balance. Balance is positive when
        the tenant still owes."""
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Agreement not found.', status=404)

        entries = request.env['lhc.ledger.entry'].search(
            [('agreement_id', '=', agr.id)], order='date, id')

        rows = []
        balance = 0.0
        total_debit = 0.0
        total_credit = 0.0
        for e in entries:
            debit = e.debit or 0.0
            credit = e.credit or 0.0
            balance += debit - credit
            total_debit += debit
            total_credit += credit
            rows.append({
                'id': e.id,
                'date': e.date.strftime('%d %b %Y') if e.date else '',
                'type': e.entry_type or '',
                'type_label': self._LEDGER_TYPES.get(e.entry_type, e.entry_type or ''),
                'description': e.description or '',
                'receipt_no': e.receipt_no or '',
                'debit': debit,
                'credit': credit,
                'balance': balance,
            })

        return api_success(
            data={
                'agreement_id': agr.id,
                'tenant': agr.primary_tenant_id.name or '',
                'unit': agr.unit_id.code or '',
                'summary': {
                    'debit': total_debit,
                    'credit': total_credit,
                    'balance': balance,
                },
                'entries': rows,
            },
            message='Ledger loaded.',
        )

    @http.route(f'{API_ROOT}/agreements/<int:agreement_id>', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def agreement_detail(self, agreement_id, **kwargs):
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Agreement not found.', status=404)

        tenant = agr.primary_tenant_id
        entity = agr.billing_entity_id
        unit = agr.unit_id

        return api_success(
            data={
                'agreement_id': agr.id,
                'name': agr.name or '',
                'template': agr.template_id.name or '',
                'status': agr.state or '',
                'payment_status': self._payment_status(agr),

                'tenant': {
                    'id': tenant.id,
                    'name': tenant.name or '',
                    'phone': tenant.mobile or '',
                    'email': tenant.email or '',
                },

                'unit': unit.code or '',
                'property': unit.property_id.name or '',

                # Billing & bank — "owner" is the billing entity; "rent credited
                # to" is its bank label, shown masked on the web form too.
                'owner': entity.name or '',
                'gst_applicable': bool(agr.gst_applicable),
                'tax_label': 'GST' if agr.gst_applicable else 'Non-GST',
                'bank_label': agr.bank_label or '',

                # Rent & deposit
                'monthly_rent': agr.payable_rent or 0.0,
                'deposit': agr.advance_total or 0.0,
                'advance_collected': agr.advance_collected or 0.0,
                'advance_balance': agr.advance_balance or 0.0,

                # Dates & terms
                'start_date': self._fmt(agr.start_date),
                'end_date': self._fmt(agr.end_date),
                'due_day': agr.due_day or 0,
                'notice_period_days': agr.notice_period_days or 0,
                'lockin_months': agr.lockin_months or 0,
                'escalation_pct': agr.escalation_pct or 0.0,
                'escalation_frequency':
                    _ESCALATION_FREQ.get(agr.escalation_frequency, ''),
                'deposit_escalates': bool(agr.deposit_escalates),

                'pending_maintenance': self._pending_maintenance(agr),
            },
            message='Agreement loaded.',
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt(d):
        return d.strftime('%d %b %Y') if d else ''

    @staticmethod
    def _payment_status(agr):
        """This month's status for the agreement: paid / partial / overdue.

        Uses the same rule as the dues endpoint — approved receipts this month
        compared to the rent payable — so the badge on the detail screen agrees
        with the list the user tapped from.
        """
        today = fields.Date.today()
        month_start = today.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        received = sum(request.env['lhc.receipt'].search([
            ('agreement_id', '=', agr.id),
            ('state', '=', 'approved'),
            ('receipt_date', '>=', month_start),
            ('receipt_date', '<', next_month),
        ]).mapped('rent_amount'))
        payable = agr.payable_rent or 0.0
        if payable - received <= _EPSILON:
            return 'paid'
        return 'partial' if received > _EPSILON else 'overdue'

    @staticmethod
    def _pending_maintenance(agr):
        """Tenant-payable maintenance on this unit still to be recovered.

        Mirrors the "Pending Maintenance" card. Empty when the unit has none or
        when maintenance is not tracked against the unit.
        """
        if not agr.unit_id:
            return []
        records = request.env['lhc.maintenance'].search([
            ('unit_id', '=', agr.unit_id.id),
            ('payable_by', '=', 'tenant'),
            ('recovery_status', '=', 'pending'),
        ], order='date desc')
        return [{
            'id': m.id,
            'title': m.expense_type or (m.name or ''),
            'vendor': m.vendor or '',
            'date': MobileAgreementDetail._fmt(m.date),
            'amount': m.amount or 0.0,
        } for m in records]
