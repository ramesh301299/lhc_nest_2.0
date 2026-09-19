# -*- coding: utf-8 -*-
"""End-to-end tests for ``/api/mobile/profile``.

These run over real HTTP with a real bearer token, because the things worth
asserting only exist at that level: the envelope, the status codes, and — the
reason this file exists — that a plain LHC NEST user with no Odoo
administration rights can change their *own* name, email, phone, designation
and picture, and nothing else.

That permission is not implemented in the controller. It comes from
``res.users.write()`` consulting ``SELF_WRITEABLE_FIELDS``, which ``lhc_nest``
extends. The controller merely builds a dict of those fields, which is exactly
what the Odoo web Preferences dialog does — so these tests are equally a
statement about what the web profile flow allows.
"""
import base64
import json
import struct
import zlib

from odoo.tests.common import HttpCase, new_test_user, tagged


def _png(width=48, height=48, rgb=(214, 160, 70)):
    """A real PNG, built without Pillow.

    The upload endpoint sniffs the bytes rather than trusting a filename, so a
    test fixture has to be a genuine image for the happy path to be exercised.
    """
    raw = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))

    def chunk(kind, payload):
        body = kind + payload
        return (struct.pack('>I', len(payload)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))


@tagged('post_install', '-at_install', 'lhc', 'mobile_api', 'lhc_profile')
class TestMobileProfile(HttpCase):

    def setUp(self):
        super().setUp()
        # Deliberately *only* the LHC role: no group_system, no
        # group_erp_manager. If the fields were not self-service, every write
        # below would fail — which is the point of testing as this user.
        self.user = new_test_user(
            self.env, login='mobile_profile_admin',
            groups='lhc_nest.group_lhc_admin', name='Profile Tester')
        token, __ = self.env['mobile.access.token']._issue(self.user)
        self.headers = {'Authorization': 'Bearer %s' % token,
                        'Content-Type': 'application/json'}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get(self, path, headers=None):
        return self.url_open(path, headers=self.headers if headers is None else headers)

    def _post(self, path, payload, headers=None):
        return self.url_open(
            path, data=json.dumps(payload).encode(),
            headers=self.headers if headers is None else headers)

    def _data(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['success'], body)
        return body['data']

    # ------------------------------------------------------------------
    # Browser reachability
    # ------------------------------------------------------------------
    def test_the_cors_preflight_allows_both_methods(self):
        """The Flutter *web* build cannot save without this.

        A bearer token makes every request non-simple, so a browser sends an
        OPTIONS preflight first and refuses to send the real request unless
        the method it wants is in `Access-Control-Allow-Methods`. Odoo fills
        that header from the single routing rule Werkzeug matched — so if GET
        and POST are ever split back into two rules on the same path, the
        preflight advertises one of them and the other dies in the browser,
        with nothing in the server log to show for it.
        """
        for path in ('/api/mobile/profile', '/api/mobile/profile/avatar'):
            response = self.opener.options(
                self.base_url() + path,
                headers={'Origin': 'http://localhost:8080',
                         'Access-Control-Request-Method': 'POST'})
            self.assertEqual(response.status_code, 204, path)
            allowed = response.headers.get('Access-Control-Allow-Methods', '')
            self.assertIn('GET', allowed, path)
            self.assertIn('POST', allowed, path)
            self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), '*')
            self.assertIn(
                'Authorization',
                response.headers.get('Access-Control-Allow-Headers', ''), path)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def test_profile_requires_a_token(self):
        """No bearer token is a clean 401, not an HTML login page."""
        response = self._get('/api/mobile/profile', headers={})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_profile_returns_the_callers_own_record(self):
        data = self._data(self._get('/api/mobile/profile'))
        self.assertEqual(data['user_id'], self.user.id)
        self.assertEqual(data['name'], 'Profile Tester')
        self.assertEqual(data['role'], 'admin')
        # Nothing sensitive travels with it.
        self.assertNotIn('password', data)

    def test_an_unset_char_is_an_empty_string_not_false(self):
        """The app renders these directly; Odoo's `False` must not reach it."""
        data = self._data(self._get('/api/mobile/profile'))
        self.assertEqual(data['phone'], '')
        self.assertEqual(data['designation'], '')

    def test_odoos_generated_svg_does_not_count_as_a_profile_picture(self):
        """The trap this endpoint has to sidestep.

        `res.users.create` stores a generated SVG of the user's initials in
        `image_1920`, so the field is set for every internal user from the
        moment they exist. Reporting that as a picture would mean the app never
        drew its own initials and instead requested an SVG it cannot decode.
        """
        self.assertTrue(self.user.image_1920, 'precondition: Odoo generates one')

        data = self._data(self._get('/api/mobile/profile'))
        self.assertFalse(data['has_avatar'])
        self.assertEqual(data['avatar_path'], '')
        # And asking for it anyway is a clean 404, not an SVG.
        self.assertEqual(self._get('/api/mobile/profile/avatar').status_code, 404)

    def test_an_svg_upload_is_rejected(self):
        """Same reason: the app cannot draw one."""
        svg = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>"
        response = self._post('/api/mobile/profile/avatar',
                              {'image': base64.b64encode(svg).decode()})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['errors'][0]['field'], 'image')

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def test_a_plain_lhc_user_can_edit_their_own_four_fields(self):
        data = self._data(self._post('/api/mobile/profile', {
            'name': 'Renamed Tester',
            'email': 'renamed@example.com',
            'phone': '+91 98765 43210',
            'designation': 'Owner · Admin',
        }))

        self.assertEqual(data['name'], 'Renamed Tester')
        self.assertEqual(data['phone'], '+91 98765 43210')
        self.assertEqual(data['designation'], 'Owner · Admin')

        # Persisted, not merely echoed.
        self.user.invalidate_recordset()
        self.assertEqual(self.user.name, 'Renamed Tester')
        self.assertEqual(self.user.phone, '+91 98765 43210')
        self.assertEqual(self.user.function, 'Owner · Admin')

    def test_reopening_the_screen_shows_the_saved_values(self):
        """Requirement in plain terms: close the form, open it, see the change."""
        self._post('/api/mobile/profile', {'designation': 'Managing Partner'})
        data = self._data(self._get('/api/mobile/profile'))
        self.assertEqual(data['designation'], 'Managing Partner')

    def test_an_absent_field_is_left_alone(self):
        """A partial payload must not blank the fields it does not mention."""
        self._post('/api/mobile/profile', {'phone': '+91 90000 00001'})
        self._post('/api/mobile/profile', {'name': 'Only The Name'})

        data = self._data(self._get('/api/mobile/profile'))
        self.assertEqual(data['name'], 'Only The Name')
        self.assertEqual(data['phone'], '+91 90000 00001')

    def test_an_empty_string_clears_the_field(self):
        self._post('/api/mobile/profile', {'phone': '+91 90000 00002'})
        self._post('/api/mobile/profile', {'phone': ''})
        self.assertEqual(self._data(self._get('/api/mobile/profile'))['phone'], '')

    def test_a_blank_name_is_rejected(self):
        response = self._post('/api/mobile/profile', {'name': '   '})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['errors'][0]['field'], 'name')
        # And nothing was written.
        self.user.invalidate_recordset()
        self.assertEqual(self.user.name, 'Profile Tester')

    def test_a_malformed_email_is_rejected(self):
        response = self._post('/api/mobile/profile', {'email': 'not-an-email'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['errors'][0]['field'], 'email')

    def test_changing_the_email_does_not_change_the_login(self):
        """Exactly as in the web Preferences dialog — the two are not the same."""
        self._post('/api/mobile/profile', {'email': 'new.address@example.com'})
        data = self._data(self._get('/api/mobile/profile'))
        self.assertEqual(data['email'], 'new.address@example.com')
        self.assertEqual(data['login'], 'mobile_profile_admin')

    def test_the_endpoint_cannot_be_used_to_write_anything_else(self):
        """A field the app does not offer is ignored, not passed through."""
        self._post('/api/mobile/profile', {'login': 'hijacked@example.com',
                                           'name': 'Still Me'})
        self.user.invalidate_recordset()
        self.assertEqual(self.user.login, 'mobile_profile_admin')
        self.assertEqual(self.user.name, 'Still Me')

    # ------------------------------------------------------------------
    # Profile picture
    # ------------------------------------------------------------------
    def test_uploading_a_picture_persists_and_is_served_back(self):
        image = base64.b64encode(_png()).decode()
        data = self._data(self._post('/api/mobile/profile/avatar', {
            'image': image, 'filename': 'me.png'}))

        self.assertTrue(data['has_avatar'])
        self.assertTrue(data['avatar_path'].startswith('/api/mobile/profile/avatar?v='))

        # Stored on the same field the web Preferences dialog uploads to.
        self.user.invalidate_recordset()
        self.assertTrue(self.user.image_1920)

        served = self._get(data['avatar_path'])
        self.assertEqual(served.status_code, 200)
        self.assertTrue(served.headers['Content-Type'].startswith('image/'))
        self.assertTrue(served.content)

    def test_the_avatar_url_changes_when_the_picture_does(self):
        """What makes a new photo appear without the app being restarted.

        The app caches images by URL. If the URL did not move, the old picture
        would stay on screen until the cache was dropped. Two uploads in the
        same second have to be told apart, which is why the stamp is a digest
        of the bytes and not a write timestamp.
        """
        first = self._data(self._post('/api/mobile/profile/avatar', {
            'image': base64.b64encode(_png(rgb=(10, 20, 30))).decode()}))
        second = self._data(self._post('/api/mobile/profile/avatar', {
            'image': base64.b64encode(_png(rgb=(200, 100, 50))).decode()}))
        self.assertNotEqual(first['avatar_version'], second['avatar_version'])
        self.assertNotEqual(first['avatar_path'], second['avatar_path'])

    def test_editing_details_does_not_change_the_avatar_url(self):
        """The corollary: a name change must not re-download the photo."""
        before = self._data(self._post('/api/mobile/profile/avatar', {
            'image': base64.b64encode(_png()).decode()}))
        after = self._data(self._post('/api/mobile/profile',
                                      {'name': 'Renamed Again'}))
        self.assertEqual(before['avatar_version'], after['avatar_version'])

    def test_a_file_that_is_not_an_image_is_rejected(self):
        response = self._post('/api/mobile/profile/avatar', {
            'image': base64.b64encode(b'this is a text file, not a picture').decode(),
            'filename': 'sneaky.png'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['errors'][0]['field'], 'image')

    def test_malformed_base64_is_rejected(self):
        response = self._post('/api/mobile/profile/avatar', {'image': 'not base64!!'})
        self.assertEqual(response.status_code, 422)

    def test_uploading_a_picture_requires_a_token(self):
        response = self._post(
            '/api/mobile/profile/avatar',
            {'image': base64.b64encode(_png()).decode()},
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 401)
        # Nothing was stored: the account still has no picture of its own.
        # Asserted through the API because `image_1920` is never empty — Odoo
        # keeps its generated SVG there.
        self.assertFalse(self._data(self._get('/api/mobile/profile'))['has_avatar'])
