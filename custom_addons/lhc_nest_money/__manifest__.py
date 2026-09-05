# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Money',
    'version': '18.0.1.0.1',
    'category': 'LHC NEST',
    'summary': 'Receipts, bills, advances, maintenance and the tenant ledger',
    'description': """
Everything that moves money.

 * Rent receipts with the Accountant/Admin approval workflow, TDS and the
   wrong-bank exception
 * Proforma and tax invoices issued before payment, plus the monthly run
 * Advance / security deposit installments
 * Maintenance and building-level expenses, including the split-equally engine
 * Tenant ledger, with the closed-month record rule
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest_leasing'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/sequences.xml',
        'report/receipt_reports.xml',
        'report/bill_reports.xml',
        'views/maintenance_views.xml',
        'views/receipt_views.xml',
        'views/bill_views.xml',
        'views/dues_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_money_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
