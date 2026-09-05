# mobile_rest_api

The dedicated REST layer between this Odoo 18 backend and the Flutter mobile
application.

This module is the **foundation only**. It ships no business endpoints. Model
APIs are added afterwards, one at a time, each as a new file under
`controllers/`.

## Status

| | |
|---|---|
| Odoo | 18.0 |
| Namespace | `/api/mobile` |
| Endpoints implemented | `GET /api/mobile/health` — nothing else, by design |
| External Python packages | none |

## Layout

```
mobile_rest_api/
├── __init__.py                     # imports + post_init_hook (JWT secret)
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   ├── base_controller.py          # shared helpers — declares no routes
│   └── health.py                   # GET /api/mobile/health
├── models/
│   ├── __init__.py
│   └── mobile_access_token.py      # JWT issue / verify / revoke
└── security/
    └── ir.model.access.csv
```

## Install

The module lives inside the `lhc_nest` folder but is mounted into Odoo as its
own top-level addon, so Odoo sees `lhc_nest` and `mobile_rest_api` as two
sibling modules. `docker-compose.yml` already carries the mount:

```yaml
- ./mobile_rest_api:/mnt/extra-addons/mobile_rest_api:cached
```

Then either install from **Odoo → Apps → Mobile REST API** (Update Apps List
first), or from the command line:

```sh
docker compose stop odoo
docker compose run --rm --no-deps odoo odoo -d lhc_nest -i mobile_rest_api --stop-after-init
docker compose up -d odoo
```

Verify:

```sh
curl -s http://localhost:8019/api/mobile/health
```

```json
{"success": true, "message": "Mobile REST API is running.",
 "data": {"module": "mobile_rest_api", "odoo_version": "18"}}
```

## Response format

Every endpoint returns the same envelope, with a matching HTTP status code.

Success:

```json
{ "success": true, "message": "Request successful.", "data": {} }
```

Error:

```json
{ "success": false, "message": "Something went wrong.", "data": {}, "errors": [] }
```

`errors` carries per-field detail for validation failures:
`[{"field": "amount", "message": "amount is required."}]`.

| Status | Raised by |
|---|---|
| 200 | success |
| 401 | missing, malformed, expired or revoked token; `AccessDenied` |
| 403 | `AccessError` — the record exists but this user may not see it |
| 404 | `MissingError` |
| 422 | `UserError` / `ValidationError`, and failed request validation |
| 500 | anything unexpected — logged server-side, generic message returned |

Internal Python and Odoo exceptions are never returned to the app. Only
`UserError`/`ValidationError`, which Odoo raises deliberately with text written
for a person to read, are passed through.

## Authentication

`Authorization: Bearer <JWT>` on every authenticated request.

Tokens are standard **HS256 JWTs**. Two independent checks run per request:

1. **Signature and expiry** — a forged or tampered token is rejected before any
   database work. The algorithm is pinned to `HS256`, so a token claiming
   `"alg": "none"` is refused rather than trusted; signatures are compared with
   `hmac.compare_digest`, which does not leak progress through timing.
2. **Database record** — the token's `jti` must still exist in
   `mobile.access.token`. This is what makes logout and revocation possible; a
   signature-only scheme cannot invalidate a token before it expires.

What is stored is the `jti`, **not** the token string. The JWT is a credential,
so keeping it out of the database means a leaked table yields nothing an
attacker can replay, while revocation still works identically. (This is the one
deliberate departure from `jwt_provider2`, which stores the token itself.)

The signing secret lives in `ir.config_parameter` under
`mobile_rest_api.jwt_secret`, generated at install by the `post_init_hook`. It
is never returned by an endpoint and never logged. Token lifetime defaults to 7
days and is configurable via `mobile_rest_api.token_lifetime_hours`.

`_issue()` and `_revoke()` are ready for the future `/api/mobile/login` and
`/api/mobile/logout` endpoints. **No login endpoint exists yet** — that is the
next step, not this one.

## Multi-company

Nothing is hardcoded — not a company id, not a user id, not an employee id.

After the token is validated, `authenticate()` switches the request into the
real user's environment with `allowed_company_ids` set from
`user.company_ids`, the active company first. From that point a future model
API just queries `request.env[...]` normally and Odoo applies the same record
rules, access rights and company rules it applies in the web client.

The company recorded on the token is honoured only while it remains one of the
user's allowed companies, so access revoked in Odoo takes effect on the next
request rather than when the token expires.

`api_user_context()` returns the caller's `user_id`, `company_id`,
`allowed_company_ids` and — only when an HR module is installed —
`employee_id`.

## Security

- Authenticated requests run as the real user, **never** as superuser.
- `sudo()` appears in exactly three places, each a technical operation that
  necessarily precedes knowing the user: the token lookup in `authenticate()`,
  the `ir.config_parameter` read for the signing secret, and the
  `ir.module.module` check in the health probe. None of them returns business
  data.
- `mobile.access.token` is granted to `base.group_system` only, so ordinary
  users cannot read the token table over RPC.
- Passwords, the JWT secret, credentials and internal Odoo fields are never
  included in a response.

## Coexistence with what already runs

This module adds only the `/api/mobile` namespace and one new model. It renames
nothing, removes nothing, and changes no existing controller, response shape,
business logic or authentication method. It does not depend on `lhc_nest`, so
neither module can break the other.

## Adding a model API later

1. Create `controllers/<model>.py`.
2. Import the shared helpers from `.base_controller` — do not re-implement the
   envelope or the auth check.
3. Route it under `API_ROOT` and decorate with `@mobile_endpoint`.
4. Add `from . import <model>` to `controllers/__init__.py`.
5. Add any new Odoo module the endpoints rely on to `depends` in
   `__manifest__.py`.

```python
from odoo import http
from odoo.http import request

from .base_controller import API_ROOT, api_success, mobile_endpoint


class MobileAttendance(http.Controller):

    @http.route(f'{API_ROOT}/attendance', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @mobile_endpoint
    def attendance(self, **kwargs):
        records = request.env['hr.attendance'].search([])   # user's env, rules apply
        return api_success(data={'attendance': records.ids})
```

`auth='public'` on the route is intentional and is not an open door: it tells
Odoo to skip its own session check so that `@mobile_endpoint` can run the
bearer-token check instead. The practical gain is that an expired token returns
clean JSON 401 rather than Odoo's HTML login redirect, which a mobile client
cannot parse.
