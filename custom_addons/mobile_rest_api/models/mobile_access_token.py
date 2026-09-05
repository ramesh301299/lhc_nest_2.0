# -*- coding: utf-8 -*-
"""Bearer-token store for the mobile REST API.

The flow mirrors the ``jwt_provider2`` scenario already proven elsewhere in this
codebase: the app signs in once, receives a token, and sends it back on every
subsequent request as ``Authorization: Bearer <token>``.

Two independent checks run on each request:

1. **Signature and expiry** — the token is a standard HS256 JWT, so a forged or
   tampered token is rejected before any database work happens.
2. **Database record** — the token's id must still exist in this table. That is
   what makes logout and revocation possible; a signature-only scheme can never
   invalidate a token before it expires.

What is stored is the token's ``jti`` (its random identifier), never the token
string itself. The JWT is a credential; keeping it out of the database means a
leaked table dump yields nothing an attacker can replay, while revocation still
works exactly the same way.

The signing secret lives in ``ir.config_parameter`` under
``mobile_rest_api.jwt_secret``. It is generated at install time, never returned
by an endpoint, and never written to the log.

No external Python package is needed: HS256 is a HMAC-SHA256 over
``base64url(header).base64url(payload)``, which the standard library does
directly. The result is an ordinary JWT that any client library — PyJWT,
dart_jsonwebtoken, jose — can read with the same secret.
"""
import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import timedelta, timezone

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: Where the HS256 signing secret is kept. Never exposed through the API.
SECRET_PARAM = 'mobile_rest_api.jwt_secret'
#: Optional override for how long an issued token stays valid, in hours.
LIFETIME_PARAM = 'mobile_rest_api.token_lifetime_hours'
DEFAULT_LIFETIME_HOURS = 24 * 7

JWT_HEADER = {'alg': 'HS256', 'typ': 'JWT'}


def _b64url_encode(raw):
    """base64url without padding, as the JWT specification requires."""
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64url_decode(segment):
    """Inverse of :func:`_b64url_encode`, restoring the stripped padding."""
    return base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4))


class MobileAccessToken(models.Model):
    _name = 'mobile.access.token'
    _description = 'Mobile REST API Access Token'
    _rec_name = 'jti'
    _order = 'expires_at desc, id desc'

    jti = fields.Char(
        string='Token ID', required=True, index=True, copy=False, readonly=True,
        help="Random identifier carried in the token's `jti` claim. The token "
             "string itself is deliberately not stored.")
    user_id = fields.Many2one(
        'res.users', string='User', required=True, index=True,
        ondelete='cascade', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Active Company', ondelete='cascade', readonly=True,
        help="Company the session started in. Always one of the user's allowed "
             "companies; it narrows the context, it never widens it.")
    expires_at = fields.Datetime(string='Expires At', required=True, readonly=True)
    is_expired = fields.Boolean(compute='_compute_is_expired')

    _sql_constraints = [
        ('jti_uniq', 'unique(jti)', 'A token identifier must be unique.'),
    ]

    @api.depends('expires_at')
    def _compute_is_expired(self):
        now = fields.Datetime.now()
        for token in self:
            token.is_expired = not token.expires_at or token.expires_at <= now

    # ------------------------------------------------------------------
    # Signing secret
    # ------------------------------------------------------------------
    @api.model
    def _get_secret(self):
        """Return the HS256 signing secret as bytes, creating it if missing.

        Normally created once by the module's ``post_init_hook``; the lazy
        branch here is a fallback for databases restored without it.
        """
        params = self.env['ir.config_parameter'].sudo()
        secret = params.get_param(SECRET_PARAM)
        if not secret:
            secret = secrets.token_urlsafe(64)
            params.set_param(SECRET_PARAM, secret)
            _logger.info('mobile_rest_api: generated a new JWT signing secret.')
        return secret.encode('utf-8')

    @api.model
    def _lifetime_hours(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(LIFETIME_PARAM)
        try:
            hours = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_LIFETIME_HOURS
        return hours if hours > 0 else DEFAULT_LIFETIME_HOURS

    # ------------------------------------------------------------------
    # Encode / decode
    # ------------------------------------------------------------------
    @api.model
    def _sign(self, claims):
        """Serialise ``claims`` into a signed HS256 JWT string."""
        segments = [
            _b64url_encode(json.dumps(part, separators=(',', ':'), sort_keys=True).encode('utf-8'))
            for part in (JWT_HEADER, claims)
        ]
        signing_input = '.'.join(segments).encode('ascii')
        signature = hmac.new(self._get_secret(), signing_input, hashlib.sha256).digest()
        segments.append(_b64url_encode(signature))
        return '.'.join(segments)

    @api.model
    def _decode(self, token):
        """Return the claims of a structurally valid, unexpired token, else None.

        Every failure path returns ``None`` rather than raising: a malformed
        token is a client mistake, not a server error, and the caller turns it
        into a plain 401.
        """
        try:
            header_b64, claims_b64, signature_b64 = token.split('.')
        except (AttributeError, ValueError):
            return None

        try:
            header = json.loads(_b64url_decode(header_b64))
            claims = json.loads(_b64url_decode(claims_b64))
            signature = _b64url_decode(signature_b64)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None

        # Pin the algorithm to what we issue. Trusting the token's own `alg`
        # is the classic JWT flaw — it lets a caller downgrade to "none" or
        # swap HMAC for RSA and hand us a signature we would happily accept.
        if not isinstance(header, dict) or header.get('alg') != 'HS256':
            return None
        if not isinstance(claims, dict):
            return None

        expected = hmac.new(
            self._get_secret(),
            f'{header_b64}.{claims_b64}'.encode('ascii'),
            hashlib.sha256,
        ).digest()
        # Constant-time comparison: a byte-by-byte `==` leaks, through timing,
        # how much of a guessed signature was correct.
        if not hmac.compare_digest(expected, signature):
            return None

        expires = claims.get('exp')
        if not isinstance(expires, (int, float)) or expires <= time.time():
            return None
        return claims

    # ------------------------------------------------------------------
    # Issue / verify / revoke
    # ------------------------------------------------------------------
    @api.model
    def _issue(self, user, company=None, lifetime_hours=None):
        """Issue a token for ``user``; return ``(token_string, record)``.

        ``company`` is honoured only when it is one of the user's allowed
        companies — a client cannot select its way into a company Odoo would
        not have given it. Anything else falls back to the user's default.

        Used by the future ``/api/mobile/login`` endpoint; nothing calls it yet.
        """
        allowed = user.company_ids
        active = company if (company and company in allowed) else user.company_id

        hours = lifetime_hours if (lifetime_hours and lifetime_hours > 0) else self._lifetime_hours()
        expires_at = fields.Datetime.now() + timedelta(hours=hours)
        jti = secrets.token_urlsafe(32)

        record = self.sudo().create({
            'jti': jti,
            'user_id': user.id,
            'company_id': active.id,
            'expires_at': expires_at,
        })
        token = self._sign({
            'jti': jti,
            'sub': user.id,
            'cid': active.id,
            'iat': int(time.time()),
            # `expires_at` is naive UTC, as all Odoo datetimes are.
            'exp': int(expires_at.replace(tzinfo=timezone.utc).timestamp()),
        })
        return token, record

    @api.model
    def _verify(self, token):
        """Return the live token record for ``token``, or an empty recordset."""
        claims = self._decode(token)
        if not claims:
            return self.browse()

        jti = claims.get('jti')
        if not isinstance(jti, str) or not jti:
            return self.browse()

        record = self.sudo().search([('jti', '=', jti)], limit=1)
        # The signature proved the token is ours and unexpired; these checks
        # cover what can change *after* it was issued — revoked, archived user.
        if not record or record.is_expired:
            return self.browse()
        if not record.user_id or not record.user_id.active:
            return self.browse()
        return record

    @api.model
    def _revoke(self, token):
        """Invalidate a token immediately. For the future logout endpoint."""
        record = self._verify(token)
        if record:
            record.sudo().unlink()
            return True
        return False

    @api.autovacuum
    def _gc_expired_tokens(self):
        """Drop expired tokens on Odoo's daily vacuum, so the table stays small."""
        expired = self.sudo().search([('expires_at', '<=', fields.Datetime.now())])
        if expired:
            _logger.info('mobile_rest_api: removing %d expired token(s).', len(expired))
            expired.unlink()
