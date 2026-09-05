# -*- coding: utf-8 -*-
{
    'name': 'Mobile REST API',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Base REST API layer for the Flutter mobile application — '
               'JWT bearer authentication, a single response envelope and a '
               'health probe under /api/mobile.',
    'description': """
Mobile REST API
===============
The dedicated REST layer between this Odoo backend and the Flutter mobile
application. It owns the **/api/mobile** namespace, which no existing Odoo,
web or third-party route uses, so it coexists with everything already running.

This is the FOUNDATION only — it deliberately ships no business endpoints.
Model APIs (Authentication, Attendance, Expense, CRM, Sales, Purchase,
Inventory, HR, Time Off, …) are added afterwards, one at a time, as new files
under ``controllers/``.

What the foundation provides
----------------------------
* ``controllers/base_controller.py`` — the reusable layer every future
  endpoint builds on: JSON request parsing, the success/error envelope, HTTP
  status codes, bearer-token authentication, the caller's identity and company
  context, field validation and exception handling. Response and auth logic is
  defined once here instead of being repeated in each controller.
* ``models/mobile_access_token.py`` — the JWT token store. Tokens are standard
  HS256 JWTs, validated by signature *and* by a database record so that
  revocation is possible.
* ``controllers/health.py`` — ``GET /api/mobile/health``, the only endpoint.

Security
--------
Every authenticated request runs as the real Odoo user, never as superuser, so
record rules, access rights and multi-company rules apply to the mobile app
exactly as they do in the web client. ``sudo()`` appears only where a technical
operation genuinely precedes knowing the user (token lookup) and is confined to
that lookup. Internal exceptions are logged server-side and never returned to
the app.

Dependencies
------------
No external Python package is required: HS256 signing uses the standard
library, so the module installs on a stock ``odoo:18`` image. The tokens are
ordinary JWTs and remain readable by any client-side JWT library.
""",
    'author': 'SDK Infinity',
    'website': 'https://www.sdkinfinity.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        # Role detection reuses lhc_nest's Admin/Accountant groups and its
        # `_user_role` mapping rather than re-deriving them, so the web app and
        # the mobile app can never disagree about who is an admin. Declaring
        # the dependency makes that requirement explicit: without it a missing
        # lhc_nest would silently reject every login instead of failing loudly.
        'lhc_nest',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
