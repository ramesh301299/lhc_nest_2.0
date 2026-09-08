# -*- coding: utf-8 -*-
{
    'name': 'LHC NEST — Theme',
    'version': '18.0.2.0.0',
    'category': 'LHC NEST',
    'summary': 'LHC NEST visual layer for the Odoo backend — Brand Bible v2.0',
    'description': """
LHC NEST Theme
==============
The visual layer for the LHC NEST application. Contains **no business models**
and no business logic — colours, typography, layout, and two OWL components
that render Odoo's own menus and actions.

 * Brand Bible v2.0 palette (navy #1a1a2e / gold #b8933a on a #f7f0de wash)
 * Fluid clamp() type and spacing scale
 * Left sidebar built from real ir.ui.menu records via Odoo's menu service
 * Quick Entries launcher — a client action dispatching existing actions
 * Restyled list, form, kanban, dialog, badge and report chrome
 * Additive kanban views for units, receipts, entities, templates and photos

Uninstalling this module returns the application to stock Odoo styling with no
loss of data, views or functionality.
""",
    'author': 'SDK Infinity',
    'website': 'https://www.lovelyhomecreators.com',
    'license': 'LGPL-3',
    # Only the base addon, never a business one: installing the theme must not
    # drag Properties, Leasing, Money and the rest in with it. The base gives
    # it the root menu and the Quick Entries parent, nothing more.
    'depends': ['web', 'lhc_nest'],
    'data': [
        'views/lhc_branding.xml',
        'views/quick_entries_views.xml',
    ],
    'assets': {
        # SCSS variable overrides must land in the primary-variables bundle so
        # every backend stylesheet compiles against them, rather than being
        # fought selector-by-selector afterwards.
        # Order matters and reads backwards: two prepends leave the LAST one
        # first, so the token file lands ahead of the override file that reads
        # from it, and both land ahead of Odoo's own `!default` declarations.
        'web._assets_primary_variables': [
            ('prepend', 'lhc_nest_theme/static/src/scss/_odoo_variables.scss'),
            ('prepend', 'lhc_nest_theme/static/src/scss/_lhc_tokens.scss'),
        ],
        # The secondary bundle is compiled separately and does not see the
        # primary one, so the tokens have to be handed to it as well or any
        # stylesheet compiled against it cannot resolve $lhc-navy. The file
        # emits no CSS of its own, so prepending it twice costs nothing.
        'web._assets_secondary_variables': [
            ('prepend', 'lhc_nest_theme/static/src/scss/_lhc_tokens.scss'),
        ],
        'web.assets_backend': [
            # Self-hosted Inter. First, so the faces are declared before any
            # sheet that sets type in them.
            'lhc_nest_theme/static/src/scss/fonts.scss',
            'lhc_nest_theme/static/src/scss/tokens.scss',
            'lhc_nest_theme/static/src/scss/layout.scss',
            'lhc_nest_theme/static/src/scss/appbar.scss',
            'lhc_nest_theme/static/src/scss/navbar.scss',
            'lhc_nest_theme/static/src/scss/sidebar.scss',
            'lhc_nest_theme/static/src/scss/controls.scss',
            'lhc_nest_theme/static/src/scss/badges.scss',
            'lhc_nest_theme/static/src/scss/list.scss',
            'lhc_nest_theme/static/src/scss/form.scss',
            'lhc_nest_theme/static/src/scss/kanban.scss',
            'lhc_nest_theme/static/src/scss/dialog.scss',
            'lhc_nest_theme/static/src/scss/states.scss',
            # Toasts. Self-contained: position, ground, accent and type all in
            # one file, so there is nowhere else for a competing rule to live.
            'lhc_nest_theme/static/src/toast/lhc_toast.scss',
            # The loading overlay. The stylesheet is shared with the login
            # bundle below, so it is written against SCSS variables rather than
            # the --lhc-* custom properties, which only exist in the backend.
            'lhc_nest_theme/static/src/loader/lhc_loader.scss',
            'lhc_nest_theme/static/src/loader/lhc_loader.xml',
            'lhc_nest_theme/static/src/dashboard/dashboard_theme.scss',
            # mobile.scss is loaded LAST on purpose. Its phone rules and the
            # dashboard's 820px rules both match a 600px viewport, so at equal
            # specificity the later file wins — load order is what decides
            # whether stat cards end up one column or two.
            'lhc_nest_theme/static/src/scss/mobile.scss',
            # The New button, floated out of the app bar into a corner FAB.
            # After mobile.scss: that file gives every `.btn` a 44px touch
            # target and a 16px inline padding at <=820px, and the compact
            # circle has to be able to say otherwise.
            'lhc_nest_theme/static/src/fab/lhc_fab.scss',
            # The search box must not take focus when a view opens.
            'lhc_nest_theme/static/src/search/lhc_search_focus.js',
            'lhc_nest_theme/static/src/appbar/systray_space.js',
            'lhc_nest_theme/static/src/mobile/list_mobile.js',
            'lhc_nest_theme/static/src/sidebar/lhc_sidebar.js',
            'lhc_nest_theme/static/src/sidebar/lhc_sidebar.xml',
            # Creating a record opens a wizard rather than replacing the
            # screen with an empty form. Patches ListController and
            # KanbanController only; the form itself is the model's own.
            # A back button on every child screen. Odoo ships one only for
            # small screens; this extends the same component so desktop gets
            # it too, using Odoo's own breadcrumb callback.
            'lhc_nest_theme/static/src/breadcrumb/lhc_back_button.xml',
            'lhc_nest_theme/static/src/create/create_dialog.js',
            'lhc_nest_theme/static/src/create/create_dialog.xml',
            'lhc_nest_theme/static/src/quick_entries/quick_entries.scss',
            'lhc_nest_theme/static/src/quick_entries/quick_entries.js',
            'lhc_nest_theme/static/src/quick_entries/quick_entries.xml',
            # Client view — the customer-facing screen for an Odoo model.
            # Reads the model's own views, fields and records through the ORM;
            # it stores nothing of its own and defines no model.
            'lhc_nest_theme/static/src/client_view/lhc_client_view.scss',
            'lhc_nest_theme/static/src/client_view/lhc_client_view.js',
            'lhc_nest_theme/static/src/client_view/lhc_client_view.xml',
        ],
        # The sign-in screen. This bundle is compiled on its own and does not
        # inherit either variable bundle, so the tokens have to be prepended
        # here too or login.scss cannot resolve $lhc-navy. The token file emits
        # no CSS of its own, so prepending it a third time costs nothing.
        'web.assets_frontend_minimal': [
            ('prepend', 'lhc_nest_theme/static/src/scss/_lhc_tokens.scss'),
            'lhc_nest_theme/static/src/scss/login.scss',
            # The same overlay on the sign-in screen. There is no webclient and
            # no RPC bus here, so a small submit handler stands in for the
            # LoadingIndicator component the backend uses.
            'lhc_nest_theme/static/src/loader/lhc_loader.scss',
            'lhc_nest_theme/static/src/loader/lhc_login_loader.js',
        ],
        # Printed documents follow the same brand, but must not inherit the
        # backend shell styles.
        'web.report_assets_common': [
            'lhc_nest_theme/static/src/scss/fonts.scss',
            'lhc_nest_theme/static/src/scss/report.scss',
        ],
    },
    # Restores the five view_mode values and the Quick Entries menu action
    # that this module writes on records owned by lhc_nest.
    'uninstall_hook': 'uninstall_hook',
    'application': True,
    'installable': True,
    'auto_install': False,
}
