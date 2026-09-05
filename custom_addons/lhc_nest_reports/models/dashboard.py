# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

ADMIN_GROUP = 'lhc_nest.group_lhc_admin'


class LhcDashboard(models.AbstractModel):
    """Server-side figures for the LHC NEST dashboard.

    An AbstractModel, so it holds no table — it is a place for the query logic
    to live rather than a record type. Putting it here instead of in a
    controller means three things:

    * every search runs as the **calling user**, with no ``sudo()``, so record
      rules and the active-company filter apply to the counts automatically —
      the numbers a user sees always match the records they can open;
    * the same method can back the future mobile API without the figures being
      computed a second, slightly different way; and
    * each card ships the *action* that opens it, built from the module's real
      actions, so a click lands on the configured views rather than a
      re-invented list.
    """
    _name = 'lhc.dashboard'
    _description = 'LHC NEST Dashboard'

    # ------------------------------------------------------------------
    def _month_bounds(self):
        """First day of this month and of the next — the collection window."""
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        nxt = (start.replace(year=start.year + 1, month=1)
               if start.month == 12 else start.replace(month=start.month + 1))
        return today, start, nxt

    def _action(self, xml_id, domain=None, context=None):
        """An act_window for a card, reusing the module's configured action.

        Loading the real action keeps the list/form views, search view and
        default filters the menu already uses; only the domain narrows.
        Returns None when the user may not run it, and the card renders as a
        plain figure instead of a broken link.
        """
        try:
            action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
        except (ValueError, AttributeError):
            return None
        if domain is not None:
            action['domain'] = domain
        if context:
            action['context'] = dict(action.get('context') or {}, **context)
        return action

    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self):
        """Every figure on the dashboard, computed from live records."""
        today, month_start, next_month = self._month_bounds()

        Unit = self.env['lhc.unit']
        Prop = self.env['lhc.property']
        Agreement = self.env['lhc.agreement']
        Receipt = self.env['lhc.receipt']
        Maintenance = self.env['lhc.maintenance']
        Vacate = self.env['lhc.vacate']

        total_units = Unit.search_count([])
        occupied = Unit.search_count([('status', '=', 'occupied')])
        vacant = Unit.search_count([('status', '=', 'vacant')])
        booked = Unit.search_count([('status', '=', 'booked')])
        total_props = Prop.search_count([])

        active_agr = Agreement.search([('state', 'in', ('active', 'notice'))])
        month_due = sum(active_agr.mapped('payable_rent'))

        month_domain = [('state', '=', 'approved'),
                        ('receipt_date', '>=', month_start),
                        ('receipt_date', '<', next_month)]
        month_receipts = Receipt.search(month_domain)
        received = sum(month_receipts.mapped('rent_amount'))

        maint_domain = [('date', '>=', month_start), ('date', '<', next_month)]
        month_maint = Maintenance.search(maint_domain)

        # Shortfall per agreement -> overdue. Computed from this month's
        # approved receipts rather than a stored flag, so it cannot go stale.
        received_by_agreement = {}
        for receipt in month_receipts:
            key = receipt.agreement_id.id
            received_by_agreement[key] = received_by_agreement.get(key, 0.0) + receipt.rent_amount
        overdue = active_agr.filtered(
            lambda a: received_by_agreement.get(a.id, 0.0) < (a.payable_rent or 0.0) - 0.01)

        soon = today + timedelta(days=30)
        expiring = active_agr.filtered(lambda a: a.end_date and today <= a.end_date <= soon)

        pending_approvals = Receipt.search_count([('state', '=', 'pending')])
        vacate_pending = Vacate.search_count([('state', '=', 'draft')])

        def pct(part, whole):
            return round((part / whole) * 100) if whole else 0

        cards = [
            {'key': 'properties', 'label': 'Properties', 'value': total_props,
             'group': 'portfolio', 'icon': 'fa-building-o',
             'action': self._action('lhc_nest_properties.action_lhc_property', [])},
            {'key': 'units', 'label': 'Units', 'value': total_units,
             'group': 'portfolio', 'icon': 'fa-home',
             'action': self._action('lhc_nest_properties.action_lhc_unit', [])},
            {'key': 'occupied', 'label': 'Occupied', 'value': occupied,
             'group': 'portfolio', 'icon': 'fa-check', 'tone': 'success',
             'sub': '%d%% occupancy' % pct(occupied, total_units),
             'action': self._action('lhc_nest_properties.action_lhc_unit',
                                    [('status', '=', 'occupied')])},
            {'key': 'vacant', 'label': 'Vacant', 'value': vacant,
             'group': 'portfolio', 'icon': 'fa-square-o', 'tone': 'warning',
             'action': self._action('lhc_nest_properties.action_lhc_unit',
                                    [('status', '=', 'vacant')])},
            {'key': 'booked', 'label': 'Booked', 'value': booked,
             'group': 'portfolio', 'icon': 'fa-bookmark-o',
             'action': self._action('lhc_nest_properties.action_lhc_unit',
                                    [('status', '=', 'booked')])},

            {'key': 'month_due', 'label': 'Rent Due This Month', 'value': month_due,
             'group': 'money', 'icon': 'fa-calendar', 'monetary': True,
             'action': self._action('lhc_nest_leasing.action_lhc_agreement',
                                    [('state', 'in', ('active', 'notice'))])},
            {'key': 'received', 'label': 'Received', 'value': received,
             'group': 'money', 'icon': 'fa-money', 'monetary': True, 'tone': 'success',
             'sub': '%d%% collected' % pct(received, month_due),
             'action': self._action('lhc_nest_money.action_lhc_receipt', month_domain)},
            {'key': 'pending', 'label': 'Pending', 'value': month_due - received,
             'group': 'money', 'icon': 'fa-hourglass-half', 'monetary': True, 'tone': 'warning',
             'action': self._action('lhc_nest_leasing.action_lhc_agreement',
                                    [('id', 'in', overdue.ids)])},
            {'key': 'maintenance', 'label': 'Maintenance This Month',
             'value': sum(month_maint.mapped('amount')),
             'group': 'money', 'icon': 'fa-wrench', 'monetary': True,
             'sub': '%d entries' % len(month_maint),
             'action': self._action('lhc_nest_money.action_lhc_maintenance', maint_domain)},

            {'key': 'active_agreements', 'label': 'Active Agreements',
             'value': len(active_agr), 'group': 'action', 'icon': 'fa-file-text-o',
             'action': self._action('lhc_nest_leasing.action_lhc_agreement',
                                    [('state', 'in', ('active', 'notice'))])},
            {'key': 'overdue', 'label': 'Overdue Tenants', 'value': len(overdue),
             'group': 'action', 'icon': 'fa-exclamation-triangle', 'tone': 'danger',
             'action': self._action('lhc_nest_leasing.action_lhc_agreement',
                                    [('id', 'in', overdue.ids)])},
            {'key': 'expiring', 'label': 'Expiring in 30 Days', 'value': len(expiring),
             'group': 'action', 'icon': 'fa-bell-o', 'tone': 'warning',
             'action': self._action('lhc_nest_leasing.action_lhc_renewals',
                                    [('id', 'in', expiring.ids)])},
            {'key': 'pending_approvals', 'label': 'Receipts Awaiting Approval',
             'value': pending_approvals, 'group': 'action', 'icon': 'fa-check-square-o',
             'tone': 'warning',
             'action': self._action('lhc_nest_money.action_lhc_approval_queue',
                                    [('state', '=', 'pending')])},
            {'key': 'vacate', 'label': 'Vacate Checklists Open',
             'value': vacate_pending, 'group': 'action', 'icon': 'fa-archive',
             'action': self._action('lhc_nest_leasing.action_lhc_vacate',
                                    [('state', '=', 'draft')])},
        ]

        return {
            'period': today.strftime('%B %Y'),
            'company': self.env.company.name,
            'currency_id': self.env.company.currency_id.id,
            'is_admin': self.env.user.has_group(ADMIN_GROUP),
            'cards': cards,
            'entities': self._entity_rows(active_agr, month_receipts),
            'overdue_tenants': self._overdue_rows(overdue, received_by_agreement, month_start),
        }

    # ------------------------------------------------------------------
    def _entity_rows(self, active_agr, month_receipts):
        """Collection per billing entity — Admin only, as in the web app.

        Not sudo'd: an accountant simply gets an empty list, and billing
        entities they may not read never load.
        """
        if not self.env.user.has_group(ADMIN_GROUP):
            return []
        rows = []
        for entity in self.env['lhc.billing.entity'].search([]):
            due = sum(active_agr.filtered(
                lambda a: a.billing_entity_id == entity).mapped('payable_rent'))
            got = sum(month_receipts.filtered(
                lambda r: r.billing_entity_id == entity).mapped('rent_amount'))
            if not due and not got:
                continue
            rows.append({'name': entity.name, 'due': due,
                         'received': got, 'pending': due - got})
        return rows

    def _overdue_rows(self, overdue, received_by_agreement, month_start):
        """Follow-up list: who is short, on which unit, by how much."""
        rows = []
        for agreement in overdue:
            shortfall = (agreement.payable_rent or 0.0) - received_by_agreement.get(agreement.id, 0.0)
            due_day = min(agreement.due_day or 5, 28)
            rows.append({
                'id': agreement.id,
                'tenant': agreement.primary_tenant_id.name or '',
                'unit': agreement.unit_id.code or '',
                'due_since': month_start.replace(day=due_day).strftime('%d %b %Y'),
                'amount': shortfall,
            })
        return rows
