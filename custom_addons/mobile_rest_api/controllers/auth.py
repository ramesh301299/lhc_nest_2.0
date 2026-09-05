# -*- coding: utf-8 -*-
"""Mobile login — ``POST /api/mobile/login``.

Credentials are verified by Odoo's own ``res.users.authenticate()``, the exact
call the web client's login goes through. Password hashing, the built-in
login rate-limiter (``_assert_can_auth``) and any auth add-on installed in this
database therefore apply unchanged — nothing about credential checking is
reimplemented here.

The token is then issued by ``mobile.access.token``, the JWT layer this module
already owns, so no second authentication system is introduced.

Role comes from the LHC NEST security groups, imported from ``lhc_nest`` rather
than re-derived, so there is one definition of "admin" across the web app and
the mobile app. Only Admin may use the mobile application; the check runs here,
in the backend, so the restriction holds regardless of which client is calling.
"""
from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

# Reused, not reimplemented: `lhc_nest` already maps a user to an LHC role for
# the web app. Importing it keeps a single source of truth — if the web app's
# role rules change, the mobile app follows automatically.
from odoo.addons.lhc_nest.controllers.main import _is_lhc_user, _user_role

from .base_controller import (
    API_ROOT,
    api_error,
    api_success,
    missing_fields,
    public_endpoint,
    request_payload,
    validation_error,
)

#: LHC roles permitted to use the mobile application. `accountant` is
#: deliberately absent: accountants use the web app only.
ALLOWED_MOBILE_ROLES = ('admin',)

NOT_AUTHORIZED_MESSAGE = 'This user is not authorized to access the mobile application.'
#: One message for "no such user" and "wrong password" alike — telling them
#: apart would let a caller enumerate which logins exist.
INVALID_CREDENTIALS_MESSAGE = 'Invalid email or password.'


class MobileAuth(http.Controller):

    @http.route(f'{API_ROOT}/login', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    @public_endpoint
    def login(self, **kwargs):
        payload = request_payload()
        email = (payload.get('email') or '').strip()
        password = payload.get('password') or ''

        errors = missing_fields({'email': email, 'password': password},
                                ['email', 'password'])
        if errors:
            return validation_error(errors, 'Email and password are required.')

        credential = {'type': 'password', 'login': email, 'password': password}
        try:
            auth_info = request.env['res.users'].authenticate(
                request.db, credential, {'interactive': False})
        except AccessDenied:
            # Covers a wrong password, an unknown login and a rate-limited
            # caller. The real reason is in the server log, never in the reply.
            return api_error(INVALID_CREDENTIALS_MESSAGE, status=401)

        # sudo() is confined to reading the group membership and employee link
        # of the user who has *just proved their identity* — the request is
        # still running as the public user at this point, so there is no other
        # way to read them. No business data is touched.
        user = request.env['res.users'].sudo().browse(auth_info['uid'])

        # A valid Odoo user is not automatically an LHC NEST user: a portal or
        # plain internal account holds neither role and must not be labelled
        # "accountant" by default.
        if not _is_lhc_user(user):
            return api_error(NOT_AUTHORIZED_MESSAGE, status=403)

        # Order matters. `group_lhc_admin` implies `group_lhc_accountant`, so
        # every admin also carries the accountant group — `_user_role` checks
        # for admin first, which is why it is reused instead of rewritten.
        role = _user_role(user)
        if role not in ALLOWED_MOBILE_ROLES:
            return api_error(NOT_AUTHORIZED_MESSAGE, status=403)

        token, _token_record = request.env['mobile.access.token'].sudo()._issue(user)

        return api_success(
            data={
                'auth_token': token,
                'user_id': user.id,
                'name': user.name or '',
                # `email` falls back to the login, which is the email the user
                # actually typed to sign in — so the app always has an address
                # to show even on an account whose partner email is unset.
                'email': user.email or user.login or '',
                'employee_id': self._employee_id_for(user),
                'role': role,
            },
            message='Login successful.',
        )

    @staticmethod
    def _employee_id_for(user):
        """The user's own employee id, or False when HR is not installed.

        `hr` is not part of this database today, so this returns False rather
        than failing. It starts returning a real id the moment an HR module is
        installed, with no change here.
        """
        if 'hr.employee' not in request.env.registry:
            return False
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1)
        return employee.id or False
