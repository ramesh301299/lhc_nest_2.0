# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Reports',
    'version': '18.0.1.1.0',
    'category': 'LHC NEST',
    'summary': 'Dashboard, GST, TDS, bank collection and profitability',
    'description': """
Owner and statutory reporting, all read from live records.

 * Dashboard — every figure computed from the ORM, every card opening a
   filtered action
 * GST / Non-GST summary, GST remittance and auditor fees
 * TDS credit tracker for ITR filing
 * Bank-wise collection with the wrong-bank flag
 * Profitability and owner withdrawals
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest_money'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/sequences.xml',
        'views/withdrawal_views.xml',
        'views/gst_views.xml',
        'views/dashboard_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_reports_demo.xml',
    ],
    'assets': {
        # The OWL dashboard moves with the model it reads. The registry tag it
        # registers under stays "lhc_nest.dashboard" — that string is what the
        # ir.actions.client record points at, and renaming it would only break
        # the action for no gain.
        'web.assets_backend': [
            'lhc_nest_reports/static/src/dashboard/dashboard.scss',
            'lhc_nest_reports/static/src/dashboard/dashboard.js',
            'lhc_nest_reports/static/src/dashboard/dashboard.xml',
        ],
    },
    # Sets the Home Action for existing LHC users so login lands on the
    # Dashboard. Idempotent, and never overrides a home action a user chose.
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
