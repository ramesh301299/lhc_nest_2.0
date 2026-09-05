# -*- coding: utf-8 -*-
"""Mobile receipt approvals — list + approve/reject.

* ``GET  /api/mobile/receipts/pending`` — receipts the accountant posted that
  await Admin approval (the app's Review Receipts screen), with a summary
  (count + total value).
* ``POST /api/mobile/receipts/<id>/approve``
* ``POST /api/mobile/receipts/<id>/reject``
  Delegate to the model's ``action_approve`` / ``action_reject`` (both Admin-only,
  enforced there; approving posts the receipt to the ledger and is final).

Each action guards that the receipt is still ``pending``, so two admins acting at
once can't double-post — the second gets a clean 422 and the list refreshes.

All run as the real Odoo user (``@mobile_endpoint``).
"""
from odoo import fields, http
from odoo.http import request

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    missing_fields,
    mobile_endpoint,
    request_payload,
    validation_error,
)


def _receipt_json(r):
    mode_labels = dict(r._fields['payment_mode'].selection)
    return {
        'receipt_id': r.id,
        'name': r.name or '',
        'tenant': r.tenant_id.name or '',
        'unit': r.unit_id.code or '',
        'agreement_id': r.agreement_id.id if r.agreement_id else None,
        'amount': r.rent_amount or 0.0,
        'payment_mode': r.payment_mode or '',
        'payment_mode_label': mode_labels.get(r.payment_mode, ''),
        'period': r.period or '',
        'gst_applicable': bool(r.gst_applicable),
        'total_invoice': r.total_invoice or 0.0,
        'receipt_date': r.receipt_date.strftime('%d %b %Y') if r.receipt_date else '',
        'posted_by': r.posted_by.name or '',
        'posted_on': r.create_date.strftime('%d %b %Y, %I:%M %p') if r.create_date else '',
        'state': r.state or '',
    }


_RECEIPT_STATE_LABELS = {
    'draft': 'Draft',
    'pending': 'Pending Approval',
    'approved': 'Approved',
    'rejected': 'Rejected',
    'cancelled': 'Cancelled',
}


def _receipt_detail_json(r):
    mode_labels = dict(r._fields['payment_mode'].selection)
    unit = r.unit_id
    return {
        'receipt_id': r.id,
        'name': r.name or '',
        'tenant': r.tenant_id.name or '',
        'unit': unit.code or '',
        'property': unit.property_id.name or '' if unit.property_id else '',
        'agreement_id': r.agreement_id.id if r.agreement_id else None,
        'period': r.period or '',
        'receipt_date': r.receipt_date.strftime('%d %b %Y') if r.receipt_date else '',
        'payment_mode': r.payment_mode or '',
        'payment_mode_label': mode_labels.get(r.payment_mode, ''),
        'bank_label': r.bank_label or '',
        'rent_amount': r.rent_amount or 0.0,
        'gst_applicable': bool(r.gst_applicable),
        'gst_amount': r.gst_amount or 0.0,
        'maintenance_amount': r.maintenance_amount or 0.0,
        'total_invoice': r.total_invoice or 0.0,
        'tds_applicable': bool(r.tds_applicable),
        'tds_amount': r.tds_amount or 0.0,
        'amount_received_bank': r.amount_received_bank or 0.0,
        'posted_by': r.posted_by.name or '',
        'approved_by': r.approved_by.name or '',
        'state': r.state or '',
        'state_label': _RECEIPT_STATE_LABELS.get(r.state, r.state or ''),
    }


class MobileReceipts(http.Controller):

    @http.route(f'{API_ROOT}/receipts/<int:receipt_id>', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def receipt_detail(self, receipt_id, **kwargs):
        r = request.env['lhc.receipt'].browse(receipt_id)
        if not r.exists():
            return api_error('Receipt not found.', status=404)
        return api_success(data=_receipt_detail_json(r), message='Receipt loaded.')


    @http.route(f'{API_ROOT}/receipts/pending', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def pending(self, **kwargs):
        receipts = request.env['lhc.receipt'].search(
            [('state', '=', 'pending')], order='create_date desc, id desc')
        rows = [_receipt_json(r) for r in receipts]
        total_value = sum(r.rent_amount or 0.0 for r in receipts)

        return api_success(
            data={
                'summary': {'count': len(rows), 'total_value': total_value},
                'receipts': rows,
            },
            message='Pending receipts loaded.',
        )

    @http.route(f'{API_ROOT}/receipts/<int:receipt_id>/approve', type='http',
                auth='public', methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def approve(self, receipt_id, **kwargs):
        return self._act(receipt_id, approve=True)

    @http.route(f'{API_ROOT}/receipts/<int:receipt_id>/reject', type='http',
                auth='public', methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def reject(self, receipt_id, **kwargs):
        return self._act(receipt_id, approve=False)

    # ------------------------------------------------------------------
    # Post Rent — posted receipts list, the agreement picker, and create.
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/receipts', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def posted(self, **kwargs):
        """Finalised (approved) receipts — the Post Rent list. Collected total is
        the rent actually posted this list."""
        receipts = request.env['lhc.receipt'].search(
            [('state', '=', 'approved')], order='receipt_date desc, id desc')
        rows = [_receipt_json(r) for r in receipts]
        collected = sum(r.rent_amount or 0.0 for r in receipts)
        return api_success(
            data={
                'summary': {'count': len(rows), 'collected': collected},
                'receipts': rows,
            },
            message='Receipts loaded.',
        )

    @http.route(f'{API_ROOT}/receipts/agreements', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def postable_agreements(self, **kwargs):
        """Active agreements to post a receipt against — the tenant picker."""
        agreements = request.env['lhc.agreement'].search(
            [('state', 'in', ('active', 'notice'))], order='name')
        rows = [{
            'agreement_id': a.id,
            'tenant': a.primary_tenant_id.name or '',
            'unit': a.unit_id.code or '',
            'property': a.unit_id.property_id.name or '' if a.unit_id.property_id else '',
            'payable_rent': a.payable_rent or 0.0,
            'gst_applicable': bool(a.gst_applicable),
            'bank_label': a.bank_label or '',
        } for a in agreements]
        return api_success(data={'agreements': rows}, message='Agreements loaded.')

    @http.route(f'{API_ROOT}/receipts', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def create_receipt(self, **kwargs):
        """Record a rent receipt. `create()` on the model auto-routes it: posted
        by an Admin (as the mobile app always is) it is approved immediately and
        posts to the ledger; the number is assigned by the model."""
        payload = request_payload()

        errors = missing_fields(
            {'agreement_id': payload.get('agreement_id'),
             'rent_amount': payload.get('rent_amount')},
            ['agreement_id', 'rent_amount'])
        if errors:
            return validation_error(errors, 'Tenant and rent amount are required.')

        try:
            agreement_id = int(payload.get('agreement_id'))
        except (TypeError, ValueError):
            return validation_error(
                [{'field': 'agreement_id', 'message': 'A valid tenant is required.'}])
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Agreement not found.', status=404)

        def num(key, default=0.0):
            v = payload.get(key)
            if v in (None, ''):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        rent = num('rent_amount')
        if rent <= 0:
            return validation_error(
                [{'field': 'rent_amount', 'message': 'Enter a rent amount greater than zero.'}])

        tds_applicable = bool(payload.get('tds_applicable'))
        tds_amount = num('tds_amount') if tds_applicable else 0.0

        vals = {
            'agreement_id': agr.id,
            'receipt_date': (payload.get('receipt_date') or '').strip()
                            or fields.Date.to_string(fields.Date.today()),
            'period': (payload.get('period') or '').strip(),
            'payment_mode': (payload.get('payment_mode') or 'upi').strip().lower(),
            'rent_amount': rent,
            'tds_applicable': tds_applicable,
            'tds_amount': tds_amount,
        }
        if agr.bank_label:
            vals['bank_label'] = agr.bank_label

        receipt = request.env['lhc.receipt'].create(vals)

        # `amount_received_bank` is deliberately NOT part of the create values.
        # It shares `_compute_amounts` with gst_amount, maintenance_amount and
        # total_invoice, and supplying any one field of a multi-field compute
        # in create() marks the whole compute as already done — so those three
        # stayed NULL and every receipt posted from the app silently lost its
        # GST and its invoice total. Letting the compute run first gives the
        # model's own default (total minus TDS, not rent minus TDS), and an
        # explicit client value is applied afterwards, leaving the totals
        # intact and re-deriving the partial/shortfall flags.
        supplied = payload.get('amount_received_bank')
        if supplied not in (None, ''):
            receipt.amount_received_bank = num(
                'amount_received_bank', receipt.amount_received_bank)

        return api_success(data=_receipt_json(receipt), message='Receipt posted.')

    @staticmethod
    def _act(receipt_id, approve):
        receipt = request.env['lhc.receipt'].browse(receipt_id)
        if not receipt.exists():
            return api_error('Receipt not found.', status=404)
        if receipt.state != 'pending':
            # Someone already acted on it (or it was never pending). The client
            # should refresh to drop it from the list.
            return api_error(
                'This receipt is no longer pending approval.', status=422,
                data={'state': receipt.state})

        # action_approve/action_reject are Admin-only (raise UserError otherwise);
        # base_controller maps that to a 422 with the model's own message.
        if approve:
            receipt.action_approve()
        else:
            receipt.action_reject()

        return api_success(
            data={'receipt_id': receipt.id, 'state': receipt.state},
            message='Receipt approved.' if approve else 'Receipt rejected.',
        )
