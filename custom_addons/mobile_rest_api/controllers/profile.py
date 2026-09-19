# -*- coding: utf-8 -*-
"""The signed-in user's own profile — read, update, avatar upload and serving.

* ``GET  /api/mobile/profile``         — the caller's profile.
* ``POST /api/mobile/profile``         — update name, email, phone, designation.
* ``POST /api/mobile/profile/avatar``  — upload a new profile picture (base64).
* ``GET  /api/mobile/profile/avatar``  — serve the picture's bytes.

The web app is the source of truth and nothing here reimplements it. Odoo's
Preferences dialog saves a profile by calling ``res.users.write()``, which
escalates to superuser *only* when every field being written is on
``SELF_WRITEABLE_FIELDS``; ``lhc_nest`` owns that list and adds ``phone`` and
``function`` to it. So this controller does exactly what the web client does —
build a dict of self-service fields and hand it to ``write()`` — and the
permission rule is enforced in one place, by Odoo, for both front ends. A field
that the web app would refuse is refused here too, without this file knowing
which fields those are.

The picture is ``image_1920``, the same field the Preferences dialog uploads
to, so a photo set on the phone shows up as the avatar in the web backend and
vice versa.

Odoo's own ``/web/image/res.users/<id>/avatar_128`` is not reused because it
authenticates with a session cookie; the app holds a bearer token. The serving
route below is the same bytes behind the same authentication as every other
mobile endpoint, and it is deliberately confined to the *caller's own* avatar.

Runs as the real Odoo user (``@mobile_endpoint``) — never as superuser.
"""
import base64
import binascii
import hashlib
import re

from odoo.http import request
from odoo import http

from odoo.tools.mimetypes import guess_mimetype

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    mobile_endpoint,
    request_payload,
    validation_error,
)

#: Deliberately permissive — "something@something.tld". Odoo itself applies no
#: format constraint to `res.partner.email`, so a stricter rule here would
#: reject addresses the web app happily saves. This only catches a typo that
#: could not possibly be an address.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

#: Decoded-bytes ceiling for an uploaded picture. The mobile client already
#: compresses to ~70% quality at 1600px, and `image_1920` re-encodes to at most
#: 1920px, so anything past this is a client that is not doing its part.
MAX_AVATAR_BYTES = 10 * 1024 * 1024

#: Fields the app may send, mapped to the Odoo field each one writes.
#: "Designation" is Odoo's Job Position (`function`) — the label differs, the
#: stored field does not.
_EDITABLE_FIELDS = {
    'name': 'name',
    'email': 'email',
    'phone': 'phone',
    'designation': 'function',
}

#: Odoo's generated "initials" avatar. `res.users.create` writes one of these
#: into `image_1920` for every internal user, so the field is never empty and
#: its presence says nothing about whether a photo was ever uploaded.
GENERATED_AVATAR_MIMETYPE = 'image/svg+xml'


def _uploaded_picture(user):
    """``(bytes, mimetype)`` of a real profile photo, or ``None``.

    Two different things live in ``image_1920``: a picture someone chose, and
    the SVG Odoo generates from the user's initials at sign-up. Only the first
    is a profile picture here — the app draws initials itself, in the LHC
    style, and cannot render SVG at all, so returning the generated one would
    be both wrong-looking and undecodable.

    Read from ``image_512`` rather than ``image_1920``: a 96px circle does not
    need a 1920px download, and Odoo has already computed and stored that size.
    """
    stored = user.image_512
    if not stored:
        return None
    try:
        data = base64.b64decode(stored)
    except (binascii.Error, ValueError):
        return None
    if not data:
        return None
    mimetype = guess_mimetype(data, default='')
    if mimetype == GENERATED_AVATAR_MIMETYPE or not mimetype.startswith('image/'):
        return None
    return data, mimetype


def _avatar_version(picture):
    """Cache key for the avatar URL — a digest of the picture itself.

    The app caches images by URL, so the URL has to change when the picture
    does or the old photo stays on screen until the app is restarted. Deriving
    it from the bytes rather than from a write timestamp gets that exactly
    right in both directions: two uploads in the same second still produce
    different URLs, and editing a name does not needlessly re-download a
    picture that has not changed.
    """
    return hashlib.sha256(picture).hexdigest()[:16] if picture else ''


def _profile_json(user):
    """Everything the app's Profile screens need, and nothing more.

    No password, no token, no group ids — the same narrow shape
    ``api_user_context`` sticks to.
    """
    picture = _uploaded_picture(user)
    has_avatar = picture is not None
    version = _avatar_version(picture[0] if picture else None)
    return {
        'user_id': user.id,
        'name': user.name or '',
        # The login is shown nowhere but is what the user actually signs in
        # with; changing `email` does not change it, exactly as in the web
        # Preferences dialog.
        'login': user.login or '',
        'email': user.email or '',
        'phone': user.phone or '',
        'designation': user.function or '',
        'role': user._lhc_role(),
        'role_label': ' · '.join(user._lhc_role_labels()),
        'company_name': user.company_id.name or '',
        'has_avatar': has_avatar,
        # Relative to the Odoo host; the app prefixes its base URL and sends
        # the bearer token when loading it. Empty when there is no picture, so
        # the app falls back to initials rather than requesting a 404.
        'avatar_path': f'{API_ROOT}/profile/avatar?v={version}' if has_avatar else '',
        'avatar_version': version,
    }


def _decoded_image(raw):
    """``(base64_string, error_response)`` for an image field from the app.

    Exactly one half is ever set. The base64 is returned rather than the bytes
    because that is what an Odoo Binary field stores; the decode happens only
    so the content can be checked before it is written.

    Accepts a bare base64 string or a data URL, the same two shapes the vacate
    photo upload accepts.
    """
    raw = (raw or '').strip()
    if not raw:
        return None, validation_error(
            [{'field': 'image', 'message': 'image is required.'}],
            'A photo is required.')

    if raw.lower().startswith('data:') and ',' in raw:
        raw = raw.split(',', 1)[1]

    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None, validation_error(
            [{'field': 'image', 'message': 'The photo is not valid base64.'}])

    if not data:
        return None, validation_error(
            [{'field': 'image', 'message': 'The photo is empty.'}])

    if len(data) > MAX_AVATAR_BYTES:
        return None, validation_error(
            [{'field': 'image',
              'message': 'The photo is too large. Please choose one under %d MB.'
                         % (MAX_AVATAR_BYTES // (1024 * 1024))}])

    # Checked on the bytes, not on the filename: a caller can name anything
    # ".jpg", and `image_1920` would raise a raw Odoo error on a non-image
    # rather than something the app can show.
    mimetype = guess_mimetype(data, default='')
    if not mimetype.startswith('image/'):
        return None, validation_error(
            [{'field': 'image', 'message': 'That file is not an image.'}])

    # An SVG is an image that the mobile client cannot draw, and storing one
    # would be indistinguishable from the placeholder Odoo generates — the
    # picture would simply never appear.
    if mimetype == GENERATED_AVATAR_MIMETYPE:
        return None, validation_error(
            [{'field': 'image',
              'message': 'Please choose a photo, not a drawing file.'}])

    return raw, None


class MobileProfile(http.Controller):

    # ------------------------------------------------------------------
    # Read and update — one route, both methods
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/profile', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, cors='*')
    @mobile_endpoint
    def profile(self, **kwargs):
        """`GET` returns the caller's profile; `POST` updates it.

        The two share a single route deliberately. Odoo answers a CORS
        preflight from whichever routing rule Werkzeug matched and fills
        ``Access-Control-Allow-Methods`` from *that rule's* ``methods``, so
        declaring GET and POST as two rules on one path makes the preflight
        advertise only one of them — and a browser then refuses to send the
        other at all. Invisible on Android and iOS, which send no preflight;
        fatal for the Flutter **web** build, where the save silently never
        leaves the browser. One rule, both methods, dispatched here.
        """
        if request.httprequest.method == 'POST':
            return self._update_profile()
        return api_success(data=_profile_json(request.env.user),
                           message='Profile loaded.')

    def _update_profile(self):
        user = request.env.user
        payload = request_payload()

        vals = {}
        for key, field in _EDITABLE_FIELDS.items():
            if key not in payload:
                # Absent means "leave alone", which is not the same as an empty
                # string meaning "clear it".
                continue
            value = payload.get(key)
            value = value.strip() if isinstance(value, str) else value
            # Odoo stores an unset Char as False, not ''.
            vals[field] = value or False

        errors = []
        if 'name' in vals and not vals['name']:
            errors.append({'field': 'name', 'message': 'Name cannot be empty.'})
        if vals.get('email') and not _EMAIL_RE.match(vals['email']):
            errors.append({'field': 'email',
                           'message': 'Enter a valid email address.'})
        if errors:
            return validation_error(errors, 'Please check the details you entered.')

        if not vals:
            return api_success(data=_profile_json(user), message='Nothing to update.')

        # The permission check. `vals` only ever holds self-service fields, so
        # this is the same escalation the Preferences dialog gets; anything
        # Odoo does not allow raises AccessError, which the envelope turns into
        # a 403 the app can show.
        user.write(vals)

        # Re-read after the write rather than echoing the request: the app is
        # then showing what the database holds, including anything an ORM
        # constraint or another module normalised on the way in.
        user.invalidate_recordset()
        return api_success(data=_profile_json(user), message='Profile updated.')

    # ------------------------------------------------------------------
    # Profile picture — one route, both methods, for the reason above
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/profile/avatar', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, cors='*')
    @mobile_endpoint
    def avatar(self, **kwargs):
        """`GET` serves the picture's bytes; `POST` replaces it."""
        if request.httprequest.method == 'POST':
            return self._upload_avatar()
        return self._avatar_image()

    def _upload_avatar(self):
        user = request.env.user
        payload = request_payload()

        raw, error = _decoded_image(payload.get('image'))
        if error:
            return error

        # `image_1920` is on SELF_WRITEABLE_FIELDS in stock Odoo — this is the
        # field the web Preferences dialog uploads to, and Odoo resizes it and
        # recomputes every `avatar_*` size from it.
        user.write({'image_1920': raw})

        user.invalidate_recordset()
        # The fresh profile carries the new `avatar_version`, so the app has
        # the cache-busting URL in the upload's own response.
        return api_success(data=_profile_json(user),
                           message='Profile picture updated.')

    def _avatar_image(self):
        picture = _uploaded_picture(request.env.user)
        if picture is None:
            # No photo of their own. The app draws its own initials in this
            # case and does not normally ask, so this is the honest answer
            # rather than Odoo's generated SVG placeholder.
            return api_error('No profile picture set.', status=404)

        data, mimetype = picture
        return request.make_response(data, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', str(len(data))),
            # Safe to cache hard: the URL carries `?v=<digest of the photo>`,
            # so a new picture is a new URL and never reads a stale entry.
            ('Cache-Control', 'private, max-age=86400'),
        ])
