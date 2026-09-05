# -*- coding: utf-8 -*-
{
    'name': 'Web Loader',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Animated dot loader for Odoo loading indicators',
    'description': """
Web Loader
==========
Replaces Odoo's default loading graphics with an animated four-dot wave.

Covers both loaders the user actually sees:

1. ``.o_loading_indicator`` - the small bottom-right "Loading" pill, shown
   250ms after any non-silent RPC. This is the one visible during ordinary
   navigation (opening records, switching views, saving).

2. ``.o_blockUI`` - the full-screen blocking overlay used for long operations.
   One rule covers all three overlays that share this markup: ``web`` (long
   saves, action switches, report generation), ``base_import`` (data import
   progress) and ``website`` (website preview loading).

The loading indicator plays the original Lottie animation through a vendored
copy of lottie-web (MIT), at static/lib/lottie/. It is served locally because
Odoo's backend CSP blocks external script hosts such as unpkg.com. The blocking
overlay uses an equivalent hand-built SVG instead, because BlockUI's template is
an inline literal that cannot be inherited.

No Python, no models, no views. Odoo's escalating "Loading... / Still
loading..." messages on the blocking overlay are left untouched.
    """,
    'author': 'ENMAC',
    'website': 'https://www.enmac.com',
    'license': 'LGPL-3',
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            # Must precede the JS below: files under static/lib are not wrapped
            # as ES modules, so this UMD bundle runs as a plain script and sets
            # window.lottie before our module is evaluated.
            'web_loader/static/lib/lottie/lottie_light.min.js',
            'web_loader/static/src/css/loader.css',
            'web_loader/static/src/js/lottie_loading_indicator.js',
            'web_loader/static/src/xml/lottie_loading_indicator.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
