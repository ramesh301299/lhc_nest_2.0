# -*- coding: utf-8 -*-
"""Mobile vacate (move-out) photos — list, detail, upload, image serving.

* ``GET  /api/mobile/vacates`` — move-out records with a move-out photo count.
* ``GET  /api/mobile/vacates/<agreement_id>`` — one move-out with its photos,
  each carrying an ``image_path`` the app can load.
* ``POST /api/mobile/vacates/<agreement_id>/photos`` — upload a room photo as
  base64; stored on ``lhc.unit.photo`` (Odoo keeps binaries base64-encoded).
* ``GET  /api/mobile/photos/<photo_id>/image`` — serve one photo's bytes, so the
  view screen shows real images by URL rather than shipping base64 in JSON.

Runs as the real Odoo user (``@mobile_endpoint``).
"""
import base64
import binascii

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

_VACATE_STATES = {'draft': 'In Progress', 'done': 'Settled'}


def _photo_json(p):
    return {
        'id': p.id,
        'room_label': p.room_label or '',
        'damage_noted': bool(p.damage_noted),
        'note': p.note or '',
        'uploaded_date': p.uploaded_date.strftime('%d %b %Y') if p.uploaded_date else '',
        # Relative to the Odoo host; the app prefixes its base URL and sends the
        # bearer token when loading it.
        'image_path': f'{API_ROOT}/photos/{p.id}/image',
    }


class MobileVacates(http.Controller):

    @http.route(f'{API_ROOT}/vacates', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def vacates(self, **kwargs):
        Photo = request.env['lhc.unit.photo']
        vacates = request.env['lhc.vacate'].search([], order='id desc')

        rows = []
        pending = 0
        for v in vacates:
            agr = v.agreement_id
            count = Photo.search_count([
                ('agreement_id', '=', agr.id),
                ('event_type', '=', 'move_out'),
            ])
            if count == 0:
                pending += 1
            rows.append({
                'id': v.id,
                'agreement_id': agr.id,
                'tenant': v.tenant_id.name or '',
                'unit': v.unit_id.code or '',
                'property': agr.unit_id.property_id.name or '' if agr.unit_id.property_id else '',
                'state': v.state or '',
                'state_label': _VACATE_STATES.get(v.state, v.state or ''),
                'vacated_date': agr.expected_vacate_date.strftime('%d %b %Y')
                                if agr.expected_vacate_date else '',
                'photo_count': count,
            })

        return api_success(
            data={
                'summary': {'total': len(rows), 'pending': pending},
                'vacates': rows,
            },
            message='Move-outs loaded.',
        )

    @http.route(f'{API_ROOT}/vacates/<int:agreement_id>', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def vacate_detail(self, agreement_id, **kwargs):
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Move-out not found.', status=404)

        photos = request.env['lhc.unit.photo'].search([
            ('agreement_id', '=', agr.id),
            ('event_type', '=', 'move_out'),
        ], order='id desc')

        return api_success(
            data={
                'agreement_id': agr.id,
                'tenant': agr.primary_tenant_id.name or '',
                'unit': agr.unit_id.code or '',
                'property': agr.unit_id.property_id.name or '' if agr.unit_id.property_id else '',
                'photos': [_photo_json(p) for p in photos],
            },
            message='Move-out loaded.',
        )

    @http.route(f'{API_ROOT}/vacates/<int:agreement_id>/photos', type='http',
                auth='public', methods=['POST'], csrf=False, cors='*')
    @mobile_endpoint
    def upload_photo(self, agreement_id, **kwargs):
        agr = request.env['lhc.agreement'].browse(agreement_id)
        if not agr.exists():
            return api_error('Move-out not found.', status=404)

        payload = request_payload()
        errors = missing_fields(
            {'room_label': payload.get('room_label'), 'image': payload.get('image')},
            ['room_label', 'image'])
        if errors:
            return validation_error(errors, 'A room and a photo are required.')

        raw = payload.get('image') or ''
        # Accept a bare base64 string or a data URL ("data:image/jpeg;base64,...").
        if ',' in raw and raw.strip().lower().startswith('data:'):
            raw = raw.split(',', 1)[1]
        try:
            base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return validation_error(
                [{'field': 'image', 'message': 'The photo is not valid base64.'}])

        photo = request.env['lhc.unit.photo'].create({
            'unit_id': agr.unit_id.id,
            'agreement_id': agr.id,
            'event_type': 'move_out',
            'room_label': (payload.get('room_label') or '').strip(),
            'image': raw,  # Odoo stores Binary fields base64-encoded.
            'image_filename': (payload.get('filename') or 'photo.jpg').strip(),
            'damage_noted': bool(payload.get('damage_noted')),
            'note': (payload.get('note') or '').strip(),
            'uploaded_date': fields.Date.to_string(fields.Date.today()),
        })
        return api_success(data=_photo_json(photo), message='Photo uploaded.')

    @http.route(f'{API_ROOT}/photos/<int:photo_id>/image', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def photo_image(self, photo_id, **kwargs):
        photo = request.env['lhc.unit.photo'].browse(photo_id)
        if not photo.exists() or not photo.image:
            return api_error('Photo not found.', status=404)
        # Binary fields come back base64-encoded; decode to the raw bytes the
        # image tag expects.
        try:
            data = base64.b64decode(photo.image)
        except (binascii.Error, ValueError):
            return api_error('Photo is unreadable.', status=422)
        return request.make_response(data, headers=[
            ('Content-Type', 'image/jpeg'),
            ('Content-Length', str(len(data))),
            ('Cache-Control', 'private, max-age=86400'),
        ])
