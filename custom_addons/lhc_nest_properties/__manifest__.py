# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST Properties',
    'version': '18.0.1.0.0',
    'category': 'LHC NEST',
    'summary': 'Properties, units, bookings and fixture purchases',
    'description': """
Properties, units and the things attached to them.

 * Properties / buildings, including the independent-villa rule that
   auto-creates a single unit so leases and ledgers behave uniformly
 * Units with occupancy status, own EB number and premises details
 * Unit bookings against a token advance
 * Fixture purchases, vendor bills and unit assignment
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    'depends': ['lhc_nest'],
    'data': [
        'security/ir.model.access.csv',
        'security/lhc_security_rules.xml',
        'data/sequences.xml',
        'views/property_views.xml',
        'views/unit_views.xml',
        'views/fixture_views.xml',
        'views/booking_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/lhc_nest_properties_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
