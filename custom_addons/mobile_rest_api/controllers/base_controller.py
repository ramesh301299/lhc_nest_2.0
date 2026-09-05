# -*- coding: utf-8 -*-
"""The reusable foundation every mobile endpoint is built on.

Nothing here is specific to a business model. Each future API — attendance,
expenses, CRM, sales — adds one controller file that imports these helpers, so
the response envelope, the authentication step and the exception handling are
written once, in this file, rather than copied into every controller.

A typical future endpoint is therefore just its business logic::

    from odoo import http
    from .base_controller import API_ROOT, api_success, mobile_endpoint

    class MobileAttendance(http.Controller):

        @http.route(f'{API_ROOT}/attendance', type='http', auth='public',
                    methods=['GET'], csrf=False, cors='*')
        @mobile_endpoint
        def attendance(self, **kwargs):
            records = request.env['hr.attendance'].search([])
            return api_success(data={'attendance': records.ids})

``auth='public'`` on the route is intentional and is *not* an open door: it
tells Odoo not to run its own session/cookie check, because ``@mobile_endpoint``
performs the bearer-token check instead and rejects anything unauthenticated
with a 401. What it buys is that an expired token returns clean JSON rather
than Odoo's HTML login redirect, which a mobile client cannot parse.
"""
import functools
import json
import logging

from odoo.exceptions import (
    AccessDenied,
    AccessError,
    MissingError,
    UserError,
    ValidationError,
)
from odoo.http import request

_logger = logging.getLogger(__name__)

#: Namespace owned by this module. Existing Odoo, web and integration routes
#: use other prefixes, so nothing added below `/api/mobile` can collide with
#: them or change an endpoint another client already depends on.
API_ROOT = '/api/mobile'

#: Returned in place of any unexpected exception. Internal Python and Odoo
#: errors are logged server-side and never travel to the mobile application.
GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.'


# ----------------------------------------------------------------------
# Responses — the single envelope every mobile endpoint returns
# ----------------------------------------------------------------------
def json_response(payload, status=200):
    return request.make_json_response(payload, status=status)


def api_success(data=None, message='Request successful.', status=200):
    """``{"success": true, "message": ..., "data": {...}}``"""
    return json_response({
        'success': True,
        'message': message,
        'data': {} if data is None else data,
    }, status=status)


def api_error(message=GENERIC_ERROR_MESSAGE, status=400, errors=None, data=None):
    """``{"success": false, "message": ..., "data": {}, "errors": [...]}``

    ``errors`` carries per-field detail (``{"field": ..., "message": ...}``)
    for validation failures; ``message`` stays human-readable for the app to
    show directly.
    """
    return json_response({
        'success': False,
        'message': message,
        'data': {} if data is None else data,
        'errors': errors or [],
    }, status=status)


# ----------------------------------------------------------------------
# Request parsing and validation
# ----------------------------------------------------------------------
def request_payload():
    """The request body as a dict — tolerant of an empty or non-JSON body.

    A bad body yields ``{}`` rather than an exception, so endpoints report the
    resulting missing fields through :func:`missing_fields` and the client gets
    a 422 listing them instead of an opaque 400.
    """
    raw = request.httprequest.get_data(as_text=True)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    # Odoo's own JSON-RPC clients nest arguments under "params"; accept either
    # shape so the Flutter app and a plain curl call both work.
    if isinstance(data, dict) and isinstance(data.get('params'), dict):
        data = data['params']
    return data if isinstance(data, dict) else {}


def query_params():
    """Query-string arguments of the current request as a plain dict."""
    return dict(request.httprequest.args)


def missing_fields(payload, required):
    """Return one ``{'field', 'message'}`` entry per absent or blank field."""
    errors = []
    for field in required:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({'field': field, 'message': '%s is required.' % field})
    return errors


def validation_error(errors, message='Some fields are invalid.'):
    """422 for a request the app can fix by correcting its input."""
    return api_error(message, status=422, errors=errors)


# ----------------------------------------------------------------------
# Authentication and caller context
# ----------------------------------------------------------------------
def bearer_token():
    """The token from ``Authorization: Bearer <token>``, or None."""
    header = request.httprequest.headers.get('Authorization') or ''
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer':
        return None
    return token.strip() or None


def authenticate():
    """Validate the bearer token and switch the request into the caller's env.

    Returns the token record, or an empty recordset when the caller is not
    authenticated.

    After this returns, the request runs as the real Odoo user — never as
    superuser — so record rules, access rights and multi-company rules apply to
    the mobile app exactly as they do in the web client. Future model APIs get
    that for free: they query ``request.env[...]`` normally and Odoo filters the
    result to what this user is allowed to see.
    """
    Token = request.env['mobile.access.token']
    token = bearer_token()
    if not token:
        return Token.browse()

    # sudo() is confined to this one lookup. Reading the token table is a
    # technical step that necessarily happens *before* any user is known, and
    # it grants no business visibility: the environment is switched to the real
    # user on the next lines, and everything downstream runs as them.
    record = Token.sudo()._verify(token)
    if not record:
        return Token.browse()

    user = record.user_id
    allowed_ids = user.company_ids.ids
    # The company stored on the token is only honoured while it remains one of
    # the user's allowed companies — access revoked in Odoo takes effect on the
    # next request, without waiting for the token to expire.
    active_id = record.company_id.id if record.company_id.id in allowed_ids else user.company_id.id
    ordered_ids = [active_id] + [cid for cid in allowed_ids if cid != active_id]

    request.update_env(
        user=user.id,
        context=dict(request.env.context, allowed_company_ids=ordered_ids),
    )
    return record


def api_user_context():
    """Identity and company context of the caller, safe to return to the app.

    Deliberately narrow: no password hash, no token, no internal Odoo fields.
    ``employee_id`` resolves only when an HR module is installed, so this stays
    correct whether or not ``hr`` is part of the database.
    """
    user = request.env.user
    company = request.env.company
    context = {
        'user_id': user.id,
        'name': user.name,
        'login': user.login,
        'company_id': company.id,
        'company_name': company.name,
        'allowed_company_ids': list(request.env.context.get('allowed_company_ids') or [company.id]),
        'employee_id': False,
    }
    if 'hr.employee' in request.env.registry:
        # Searched as the user, not with sudo(), so this reports the employee
        # record they are actually allowed to see.
        employee = request.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        context['employee_id'] = employee.id or False
    return context


# ----------------------------------------------------------------------
# Decorators
# ----------------------------------------------------------------------
def _handle_exceptions(func):
    """Map any exception to an enveloped response with the right status code.

    The subclass order matters: ``AccessDenied``, ``AccessError``,
    ``MissingError`` and ``ValidationError`` all inherit from ``UserError``, so
    each must be caught before it.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except AccessDenied:
            return api_error('Authentication failed.', 401)
        except AccessError:
            return api_error('You do not have access to this record.', 403)
        except MissingError:
            return api_error('The requested record no longer exists.', 404)
        except (ValidationError, UserError) as exc:
            # Odoo raises these deliberately, with a message written for a
            # person to read, so passing it through is safe and useful —
            # unlike a traceback, which is not.
            return api_error(str(exc), 422)
        except Exception:  # noqa: BLE001 — nothing may escape to the client
            # Roll back first: a failed request must not leave a half-written
            # transaction behind for the next one to trip over.
            try:
                request.env.cr.rollback()
            except Exception:  # noqa: BLE001
                _logger.exception('mobile_rest_api: rollback failed')
            _logger.exception('mobile_rest_api: unhandled error on %s',
                              request.httprequest.path)
            return api_error(GENERIC_ERROR_MESSAGE, 500)
    return wrapper


def mobile_endpoint(func):
    """Authenticated endpoint: valid bearer token required, errors mapped.

    Apply it directly beneath ``@http.route``.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not authenticate():
            return api_error(
                'Unauthorized. Please sign in again.',
                status=401,
                errors=[{'field': 'Authorization',
                         'message': 'A valid Bearer token is required.'}],
            )
        return func(self, *args, **kwargs)
    return _handle_exceptions(wrapper)


def public_endpoint(func):
    """Unauthenticated endpoint that still gets the envelope and error mapping.

    Only for routes that genuinely carry no user data — the health probe, and
    later the login endpoint, which has no token yet by definition.
    """
    return _handle_exceptions(func)
