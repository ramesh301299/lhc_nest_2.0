# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Tenants',
    'version': '18.0.1.0.0',
    'category': 'LHC NEST',
    'summary': 'Tenant master — individuals and company tenants',
    'description': """
The tenant master.

 * Individual and company/GST tenants
 * Authorised representative details for company tenants
 * Identity documents

Lease-derived state (current unit, status) is added by lhc_nest_leasing,
which is what keeps this addon independent of leasing.
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'views/tenant_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_tenants_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
