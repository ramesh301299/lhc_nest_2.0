# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Base',
    'summary': 'LHC NEST — foundation: roles, billing entities, shared mixins, menu skeleton',
    'description': """
LHC NEST — Foundation layer
===========================
The foundation the LHC NEST business addons build on. It deliberately holds
only what more than one of them needs:

* the two LHC NEST roles — **Admin** and **Accountant** — and their module
  category,
* **Billing Entities** (``lhc.billing.entity``): the lessor records, and the
  single source of truth for GST applicability, shared by leasing, money and
  reports,
* the **company-scoping** (``lhc.company.mixin``) and **INR-formatting**
  (``lhc.inr.mixin``) mixins every LHC model inherits,
* the **root menu and the five group headers**, which hold leaves from several
  addons and so cannot live in any one of them,
* the ``/lhc/data/*`` JSON endpoints, which ``mobile_rest_api`` reuses so the
  web app and the Flutter app can never disagree about a figure.

The business areas ship separately and can be installed independently:

* ``lhc_nest_properties``  — properties, units, bookings, fixtures
* ``lhc_nest_tenants``     — the tenant master
* ``lhc_nest_leasing``     — agreements, renewals, notice, vacate
* ``lhc_nest_money``       — receipts, bills, advances, maintenance, ledger
* ``lhc_nest_reports``     — dashboard, GST, TDS, bank collection, profitability
* ``lhc_nest_tools``       — documents, WhatsApp templates, audit trail, settings

The visual layer is ``lhc_nest_theme``, which depends on none of the above.
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'category': 'LHC NEST',
    'version': '18.0.2.0.1',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/lhc_groups.xml',
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/billing_entity_data.xml',
        'views/billing_entity_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
