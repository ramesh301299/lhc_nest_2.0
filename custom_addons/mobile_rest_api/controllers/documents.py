# -*- coding: utf-8 -*-
"""Mobile documents — list and download.

* ``GET /api/mobile/documents`` — the Documents screen: one row per file, with
  its category, what it is linked to, and who uploaded it when.
* ``GET /api/mobile/documents/<id>/file`` — the bytes, so the app opens a
  document by URL rather than carrying base64 through the list payload.

``lhc_nest_tools`` had no mobile endpoint at all, so agreements, ID proofs and
deposit receipts were reachable only from the web client.

Runs as the real Odoo user (``@mobile_endpoint``), so record rules apply.
"""
import base64
import binascii

from odoo import http
from odoo.http import request

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    mobile_endpoint,
    query_params,
)

_CATEGORY_LABELS = {
    'agreement': 'Agreement',
    'id_proof': 'ID Proof',
    'deposit_receipt': 'Deposit Receipt',
    'other': 'Other',
}

#: Content types for the formats actually uploaded here. Anything else is served
#: as a generic download rather than guessed at.
_CONTENT_TYPES = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}


def _document_json(d):
    return {
        'id': d.id,
        'name': d.name or '',
        'category': d.category or '',
        'category_label': _CATEGORY_LABELS.get(d.category, d.category or ''),
        'file_name': d.file_name or '',
        # `linked_to` is the single column the screen renders; the explicit ids
        # come too, so a tapped row can open the record it belongs to.
        'linked_to': d.linked_to or '',
        'tenant_id': d.tenant_id.id or None,
        'unit_id': d.unit_id.id or None,
        'agreement_id': d.agreement_id.id or None,
        'property_id': d.property_id.id or None,
        'upload_date': d.upload_date.strftime('%d %b %Y') if d.upload_date else '',
        'uploaded_by': d.uploaded_by.name or '',
        'note': d.note or '',
        'file_path': f'{API_ROOT}/documents/{d.id}/file',
    }


class MobileDocuments(http.Controller):

    @http.route(f'{API_ROOT}/documents', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def documents(self, **kwargs):
        params = query_params()
        domain = []

        category = (params.get('category') or '').strip().lower()
        if category in _CATEGORY_LABELS:
            domain.append(('category', '=', category))

        # Narrow to one record's documents — the Agreement / Tenant / Unit /
        # Property detail screens each show their own attachments.
        for key, field in (('tenant_id', 'tenant_id'), ('unit_id', 'unit_id'),
                           ('agreement_id', 'agreement_id'),
                           ('property_id', 'property_id')):
            raw = params.get(key)
            if raw:
                try:
                    domain.append((field, '=', int(raw)))
                except (TypeError, ValueError):
                    pass

        search = (params.get('search') or '').strip()
        if search:
            domain += ['|', ('name', 'ilike', search),
                       ('file_name', 'ilike', search)]

        records = request.env['lhc.document'].search(
            domain, order='upload_date desc, id desc')

        counts = {}
        for key in _CATEGORY_LABELS:
            counts[key] = len(records.filtered(lambda d, k=key: d.category == k))

        return api_success(
            data={
                'summary': {'count': len(records)},
                'counts': counts,
                'documents': [_document_json(d) for d in records],
            },
            message='Documents loaded.',
        )

    @http.route(f'{API_ROOT}/documents/<int:document_id>/file', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def document_file(self, document_id, **kwargs):
        doc = request.env['lhc.document'].browse(document_id)
        if not doc.exists() or not doc.file:
            return api_error('Document not found.', status=404)

        # Binary fields come back base64-encoded, whether the bytes live in the
        # filestore or the column.
        try:
            data = base64.b64decode(doc.file)
        except (binascii.Error, ValueError):
            return api_error('Document is unreadable.', status=422)

        filename = doc.file_name or ('document-%d' % doc.id)
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        content_type = _CONTENT_TYPES.get(extension, 'application/octet-stream')

        return request.make_response(data, headers=[
            ('Content-Type', content_type),
            ('Content-Length', str(len(data))),
            ('Content-Disposition', 'inline; filename="%s"' % filename),
            ('Cache-Control', 'private, max-age=3600'),
        ])
