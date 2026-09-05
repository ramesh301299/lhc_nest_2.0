# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Tools',
    'version': '18.0.1.0.0',
    'category': 'LHC NEST',
    'summary': 'Documents, WhatsApp templates, audit trail and settings',
    'description': """
Supporting tools.

 * Document register linked to properties, units, tenants and agreements
 * WhatsApp copy-to-clipboard templates (nothing is ever sent)
 * Audit trail over Odoo's own chatter tracking
 * LHC NEST settings
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest_leasing'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/wa_template_data.xml',
        'data/config_data.xml',
        'views/document_views.xml',
        'views/wa_views.xml',
        'views/audit_views.xml',
        'views/config_settings_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_tools_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
