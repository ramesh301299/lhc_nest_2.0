# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Leasing',
    'version': '18.0.1.0.0',
    'category': 'LHC NEST',
    'summary': 'Agreements, renewals, notice and vacate',
    'description': """
The lease lifecycle.

 * Agreements with versioned renewals and four escalation methods
 * Clause templates by property type
 * Joint tenants
 * Notice and vacate checklist with fixture-by-fixture settlement
 * Move-in / move-out photos

Also adds the lease-derived fields onto lhc.unit and lhc.tenant.
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest_properties', 'lhc_nest_tenants'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/sequences.xml',
        'data/agreement_template_data.xml',
        'report/agreement_reports.xml',
        'report/vacate_reports.xml',
        'views/template_views.xml',
        'views/agreement_views.xml',
        'views/advance_views.xml',
        'views/vacate_views.xml',
        'views/photo_views.xml',
        'views/tenant_ext_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_leasing_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
