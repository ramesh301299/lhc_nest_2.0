# -*- coding: utf-8 -*-
import json
import os
from datetime import timedelta

from odoo import http, fields
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.modules.module import get_module_path

# Re-exported from models/res_users.py, which is where the role now lives —
# a role is a property of the user record, not of this controller. Kept as
# module-level names because mobile_rest_api imports them from here.
from odoo.addons.lhc_nest.models.res_users import ADMIN_GROUP, ACCT_GROUP  # noqa: E402


def _user_role(user):
    """Map the logged-in user to an LHC role for the front-end."""
    return user._lhc_role()


def _is_lhc_user(user):
    """True when this login is an LHC NEST user in this database."""
    return user._lhc_is_user()


# The `LhcHome(Home)` override that used to live here is deliberately gone.
#
# It overrode `_login_redirect` and `web_client` to bounce every LHC user to
# `/lhc`, so signing in landed them in the static single-page mockup and the
# native Odoo application was unreachable except via the `/odoo?backend=1`
# escape hatch. That made index.html the actual front end and Odoo merely its
# data source — the inverse of the intended architecture.
#
# With the override removed, login follows Odoo's normal path and LHC NEST is a
# native Odoo application: its menus, views, actions, workflows and record
# rules are the application. Nothing here depends on index.html any more, so
# deleting the static file cannot break the app.


class LhcApp(http.Controller):

    @http.route('/lhc', type='http', auth='user', website=False, csrf=False)
    def lhc_app(self, **kw):
        """Serve the single-page LHC NEST app shell (the mockup, wired to live data)."""
        user = request.env.user
        path = os.path.join(get_module_path('lhc_nest'),
                            'static', 'src', 'app', 'index.html')
        with open(path, 'r', encoding='utf-8') as fh:
            html = fh.read()

        boot = {
            'role': _user_role(user),
            'name': user.name,
            'login': user.login,
        }
        html = html.replace('__LHC_BOOT__', json.dumps(boot))
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
        ])

    @http.route('/lhc/data/dashboard', type='json', auth='user')
    def lhc_dashboard(self, **kw):
        """Live figures for the dashboard cards, alerts and entity table."""
        env = request.env
        today = fields.Date.today()
        month_start = today.replace(day=1)
        # first day of next month
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        Unit = env['lhc.unit']
        Prop = env['lhc.property']
        Agr = env['lhc.agreement']
        Rec = env['lhc.receipt']
        Maint = env['lhc.maintenance']
        Vacate = env['lhc.vacate']

        total_units = Unit.search_count([])
        occupied = Unit.search_count([('status', '=', 'occupied')])
        vacant = Unit.search_count([('status', '=', 'vacant')])
        booked = Unit.search_count([('status', '=', 'booked')])
        total_props = Prop.search_count([])

        active_agr = Agr.search([('state', 'in', ('active', 'notice'))])
        month_due = sum(active_agr.mapped('payable_rent'))

        month_receipts = Rec.search([
            ('state', '=', 'approved'),
            ('receipt_date', '>=', month_start),
            ('receipt_date', '<', next_month),
        ])
        received = sum(month_receipts.mapped('rent_amount'))
        pending = month_due - received

        month_maint = Maint.search([
            ('date', '>=', month_start),
            ('date', '<', next_month),
        ])
        maint_total = sum(month_maint.mapped('amount'))
        maint_count = len(month_maint)

        # Rent received per agreement this month → any shortfall = overdue
        recv_by_agr = {}
        for rec in month_receipts:
            recv_by_agr[rec.agreement_id.id] = \
                recv_by_agr.get(rec.agreement_id.id, 0.0) + rec.rent_amount
        overdue_agr = active_agr.filtered(
            lambda a: recv_by_agr.get(a.id, 0.0) < (a.payable_rent or 0.0) - 0.01)

        # Detailed overdue list for the accountant follow-up table
        overdue_tenants = []
        for a in overdue_agr:
            shortfall = (a.payable_rent or 0.0) - recv_by_agr.get(a.id, 0.0)
            due_day = min(a.due_day or 5, 28)
            due_since = month_start.replace(day=due_day)
            overdue_tenants.append({
                'tenant': a.primary_tenant_id.name or '',
                'unit': a.unit_id.code or '',
                'due_since': due_since.strftime('%d %b %Y'),
                'amount': shortfall,
            })

        soon = today + timedelta(days=30)
        expiring = active_agr.filtered(
            lambda a: a.end_date and today <= a.end_date <= soon)

        vacate_pending = Vacate.search_count([('state', '=', 'draft')])
        pending_approvals = Rec.search_count([('state', '=', 'pending')])

        # Entity-wise collection (this month) — ADMIN ONLY (billing entities are
        # restricted to the Admin group, and the accountant UI hides this card).
        entity_rows = []
        if env.user.has_group(ADMIN_GROUP):
            for ent in env['lhc.billing.entity'].search([]):
                ent_agr = active_agr.filtered(lambda a: a.billing_entity_id == ent)
                ent_due = sum(ent_agr.mapped('payable_rent'))
                ent_recv = sum(month_receipts.filtered(
                    lambda r: r.billing_entity_id == ent).mapped('rent_amount'))
                if not ent_due and not ent_recv:
                    continue
                entity_rows.append({
                    'name': ent.name,
                    'due': ent_due,
                    'received': ent_recv,
                    'pending': ent_due - ent_recv,
                })

        occ_pct = round((occupied / total_units) * 100) if total_units else 0
        coll_pct = round((received / month_due) * 100) if month_due else 0

        return {
            'period': today.strftime('%B %Y'),
            'cards': {
                'properties': total_props,
                'units': total_units,
                'occupied': occupied,
                'vacant': vacant,
                'booked': booked,
                'occupancy_pct': occ_pct,
                'month_due': month_due,
                'received': received,
                'collected_pct': coll_pct,
                'pending': pending,
                'maintenance': maint_total,
                'maintenance_count': maint_count,
                'active_agreements': len(active_agr),
                'overdue_count': len(overdue_agr),
                'expiring_count': len(expiring),
                'vacate_count': vacate_pending,
                'pending_approvals': pending_approvals,
            },
            'entities': entity_rows,
            'overdue_tenants': overdue_tenants,
        }

    # ------------------------------------------------------------------
    # Properties & Units — live grid + create from the app
    # ------------------------------------------------------------------
    @http.route('/lhc/data/properties', type='json', auth='user')
    def lhc_properties(self, **kw):
        """Live data for the Properties & Units screen (grid, list, unit dropdown)."""
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        rows = []
        for p in env['lhc.property'].search([]):
            units = []
            for u in p.unit_ids:
                units.append({
                    'id': u.id,
                    'code': u.code or '',
                    'status': u.status,
                    'tenant': u.current_tenant_id.name or '',
                    'area_sqft': u.area_sqft,
                    'own_eb_no': u.own_eb_no or '',
                    'unit_type': u.unit_type or '',
                })
            rows.append({
                'id': p.id,
                'name': p.name,
                'code': p.code or '',
                'property_type': p.property_type,
                'location': p.location or '',
                'common_eb_no': p.common_eb_no or '',
                'unit_count': p.unit_count,
                'occupied_count': p.occupied_count,
                'vacant_count': p.vacant_count,
                'units': units,
            })
        return {'properties': rows}

    @http.route('/lhc/property/save', type='json', auth='user')
    def lhc_property_save(self, name=None, property_type='multi',
                          location=None, common_eb_no=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        name = (name or '').strip()
        if not name:
            return {'ok': False, 'error': 'Property name is required.'}
        if property_type not in ('multi', 'commercial', 'independent'):
            property_type = 'multi'
        try:
            p = env['lhc.property'].create({
                'name': name,
                'property_type': property_type,
                'location': (location or '').strip(),
                'common_eb_no': (common_eb_no or '').strip(),
            })
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'id': p.id, 'code': p.code}

    @http.route('/lhc/unit/save', type='json', auth='user')
    def lhc_unit_save(self, property_id=None, code=None, area_sqft=None,
                      own_eb_no=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        code = (code or '').strip()
        if not property_id:
            return {'ok': False, 'error': 'Property is required.'}
        if not code:
            return {'ok': False, 'error': 'Unit code is required.'}
        prop = env['lhc.property'].browse(int(property_id))
        if not prop.exists():
            return {'ok': False, 'error': 'Property not found.'}
        if env['lhc.unit'].search_count([('code', '=', code)]):
            return {'ok': False, 'error': 'A unit with that code already exists.'}
        try:
            u = env['lhc.unit'].create({
                'property_id': prop.id,
                'code': code,
                'area_sqft': float(area_sqft or 0) or 0.0,
                'own_eb_no': (own_eb_no or '').strip(),
            })
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'id': u.id}

    # ------------------------------------------------------------------
    # Tenants — live list + create/edit from the app.
    # Both roles may create/edit tenants (role matrix: tenant records = Full/Full).
    # ------------------------------------------------------------------
    @http.route('/lhc/data/tenants', type='json', auth='user')
    def lhc_tenants(self, search=None, status=None, offset=0, limit=50, **kw):
        """Paginated + searchable tenant list — the reusable list contract:
        params {search, status, offset, limit} → {rows, total, offset, limit}.
        Keeps the working set small so it scales to many records."""
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        Tenant = env['lhc.tenant']
        domain = []
        term = (search or '').strip()
        if term:
            # search covers the columns shown in the list view
            domain += ['|', '|', '|', '|',
                       ('name', 'ilike', term),
                       ('mobile', 'ilike', term),
                       ('company_name', 'ilike', term),
                       ('current_unit_id.code', 'ilike', term),
                       ('agreement_ids.name', 'ilike', term)]
        if status == 'archived':
            # Show soft-deleted records (active=False), normally hidden.
            Tenant = Tenant.with_context(active_test=False)
            domain.append(('active', '=', False))
        elif status in ('active', 'notice', 'vacated'):
            domain.append(('status', '=', status))
        try:
            offset = max(0, int(offset))
            limit = min(200, max(1, int(limit)))
        except (TypeError, ValueError):
            offset, limit = 0, 50
        total = Tenant.search_count(domain)
        rows = []
        for t in Tenant.search(domain, offset=offset, limit=limit, order='name'):
            agr = t.agreement_ids.filtered(
                lambda a: a.state in ('active', 'notice'))[:1]
            rows.append({
                'id': t.id,
                'name': t.name or '',
                'mobile': t.mobile or '',
                'unit': t.current_unit_id.code or '',
                'agreement': agr.name or '' if agr else '',
                'status': t.status or 'active',
                'tenant_type': t.tenant_type,
                'archived': not t.active,
            })
        return {'tenants': rows, 'total': total, 'offset': offset, 'limit': limit}

    @http.route('/lhc/tenant/save', type='json', auth='user')
    def lhc_tenant_save(self, name=None, tenant_type='individual', relation=None,
                        age=None, mobile=None, email=None, aadhaar=None, pan=None,
                        present_address=None, permanent_address=None,
                        company_name=None, gstin=None, rep_name=None,
                        rep_relation=None, rep_pan=None, rep_aadhaar=None,
                        rep_mobile=None, rep_address=None, tenant_id=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        name = (name or '').strip()
        if not name:
            return {'ok': False, 'error': 'Full name is required.'}
        if tenant_type not in ('individual', 'company'):
            tenant_type = 'individual'
        if tenant_type == 'company' and not (company_name or '').strip():
            return {'ok': False, 'error': 'Company / firm name is required for a GST tenant.'}
        try:
            age_val = int(age) if age not in (None, '', False) else 0
        except (TypeError, ValueError):
            age_val = 0
        vals = {
            'name': name,
            'tenant_type': tenant_type,
            'relation': (relation or '').strip(),
            'age': age_val,
            'mobile': (mobile or '').strip(),
            'email': (email or '').strip(),
            'aadhaar': (aadhaar or '').strip(),
            'pan': (pan or '').strip(),
            'present_address': (present_address or '').strip(),
            'permanent_address': (permanent_address or '').strip(),
            'company_name': (company_name or '').strip(),
            'gstin': (gstin or '').strip(),
            'rep_name': (rep_name or '').strip(),
            'rep_relation': (rep_relation or '').strip(),
            'rep_pan': (rep_pan or '').strip(),
            'rep_aadhaar': (rep_aadhaar or '').strip(),
            'rep_mobile': (rep_mobile or '').strip(),
            'rep_address': (rep_address or '').strip(),
        }
        try:
            if tenant_id:
                t = env['lhc.tenant'].browse(int(tenant_id))
                if not t.exists():
                    return {'ok': False, 'error': 'Tenant not found.'}
                t.write(vals)
            else:
                t = env['lhc.tenant'].create(vals)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'id': t.id}

    @http.route('/lhc/tenant/get', type='json', auth='user')
    def lhc_tenant_get(self, tenant_id=None, **kw):
        """Full record for the edit form."""
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        t = request.env['lhc.tenant'].browse(int(tenant_id or 0))
        if not t.exists():
            return {'ok': False, 'error': 'Tenant not found.'}
        return {'ok': True, 'tenant': {
            'id': t.id, 'name': t.name or '', 'tenant_type': t.tenant_type,
            'relation': t.relation or '', 'age': t.age or 0, 'mobile': t.mobile or '',
            'email': t.email or '', 'aadhaar': t.aadhaar or '', 'pan': t.pan or '',
            'present_address': t.present_address or '',
            'permanent_address': t.permanent_address or '',
            'company_name': t.company_name or '', 'gstin': t.gstin or '',
            'rep_name': t.rep_name or '', 'rep_relation': t.rep_relation or '',
            'rep_pan': t.rep_pan or '', 'rep_aadhaar': t.rep_aadhaar or '',
            'rep_mobile': t.rep_mobile or '', 'rep_address': t.rep_address or '',
        }}

    @http.route('/lhc/tenant/archive', type='json', auth='user')
    def lhc_tenant_archive(self, tenant_id=None, active=False, **kw):
        """Soft-delete only (spec §4.6 — never hard-delete). Toggles active."""
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        t = request.env['lhc.tenant'].with_context(active_test=False).browse(int(tenant_id or 0))
        if not t.exists():
            return {'ok': False, 'error': 'Tenant not found.'}
        t.active = bool(active)
        return {'ok': True, 'active': t.active}

    # ------------------------------------------------------------------
    # Units — flat lookup list (for assign dropdowns).
    # ------------------------------------------------------------------
    @http.route('/lhc/data/units', type='json', auth='user')
    def lhc_units(self, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        return {'units': [{
            'id': u.id,
            'code': u.code or '',
            'property': u.property_id.name or '',
        } for u in env['lhc.unit'].search([], order='code')]}

    # ------------------------------------------------------------------
    # Fixture Purchases — both roles (role matrix: Fixtures = Yes/Yes).
    # ------------------------------------------------------------------
    @http.route('/lhc/data/fixtures', type='json', auth='user')
    def lhc_fixtures(self, search=None, offset=0, limit=50, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        Fx = env['lhc.fixture.purchase']
        domain = []
        term = (search or '').strip()
        if term:
            # search covers the columns shown in the list view
            domain += ['|', '|', ('name', 'ilike', term),
                       ('vendor', 'ilike', term), ('unit_id.code', 'ilike', term)]
        try:
            offset = max(0, int(offset)); limit = min(200, max(1, int(limit)))
        except (TypeError, ValueError):
            offset, limit = 0, 50
        total = Fx.search_count(domain)
        rows = []
        for f in Fx.search(domain, offset=offset, limit=limit, order='purchase_date desc, id desc'):
            rows.append({
                'id': f.id,
                'name': f.name or '',
                'purchase_date': f.purchase_date and f.purchase_date.strftime('%d %b %Y') or '',
                'cost_before_gst': f.cost_before_gst,
                'gst_bill': f.gst_bill,
                'gst_amount': f.gst_amount,
                'vendor': f.vendor or '',
                'unit': f.unit_id.code or '',
                'has_bill': bool(f.bill_file),
                'status': f.status or '',
            })
        return {'fixtures': rows, 'total': total, 'offset': offset, 'limit': limit}

    @http.route('/lhc/fixture/save', type='json', auth='user')
    def lhc_fixture_save(self, name=None, purchase_date=None, cost_before_gst=None,
                         gst_bill=False, gst_amount=None, vendor=None, unit_id=None,
                         bill_b64=None, bill_filename=None, fixture_id=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        name = (name or '').strip()
        if not name:
            return {'ok': False, 'error': 'Item name is required.'}
        try:
            cost = float(cost_before_gst or 0)
        except (TypeError, ValueError):
            cost = 0.0
        if cost <= 0:
            return {'ok': False, 'error': 'Cost (before GST) is required.'}
        gst_bill = bool(gst_bill)
        try:
            gst_amt = float(gst_amount or 0) if gst_bill else 0.0
        except (TypeError, ValueError):
            gst_amt = 0.0
        vals = {
            'name': name,
            'cost_before_gst': cost,
            'gst_bill': gst_bill,
            'gst_amount': gst_amt,
            'vendor': (vendor or '').strip(),
        }
        if purchase_date:
            vals['purchase_date'] = purchase_date
        vals['unit_id'] = int(unit_id) if unit_id else False
        if bill_b64:
            vals['bill_file'] = bill_b64
            vals['bill_filename'] = (bill_filename or 'bill').strip()
        try:
            if fixture_id:
                f = env['lhc.fixture.purchase'].browse(int(fixture_id))
                if not f.exists():
                    return {'ok': False, 'error': 'Fixture not found.'}
                f.write(vals)
            else:
                f = env['lhc.fixture.purchase'].create(vals)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'id': f.id}

    @http.route('/lhc/fixture/get', type='json', auth='user')
    def lhc_fixture_get(self, fixture_id=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        f = request.env['lhc.fixture.purchase'].browse(int(fixture_id or 0))
        if not f.exists():
            return {'ok': False, 'error': 'Fixture not found.'}
        return {'ok': True, 'fixture': {
            'id': f.id, 'name': f.name or '',
            'purchase_date': f.purchase_date and f.purchase_date.isoformat() or '',
            'cost_before_gst': f.cost_before_gst, 'gst_bill': f.gst_bill,
            'gst_amount': f.gst_amount, 'vendor': f.vendor or '',
            'unit_id': f.unit_id.id or '', 'has_bill': bool(f.bill_file),
        }}

    @http.route('/lhc/fixture/archive', type='json', auth='user')
    def lhc_fixture_archive(self, fixture_id=None, active=False, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        f = request.env['lhc.fixture.purchase'].with_context(active_test=False).browse(int(fixture_id or 0))
        if not f.exists():
            return {'ok': False, 'error': 'Fixture not found.'}
        f.active = bool(active)
        return {'ok': True, 'active': f.active}

    # ------------------------------------------------------------------
    # Agreements — both roles create (role matrix: Create agreement = Yes/Yes).
    # ------------------------------------------------------------------
    @http.route('/lhc/data/agreement_lookups', type='json', auth='user')
    def lhc_agreement_lookups(self, **kw):
        """Dropdown sources for the New Agreement form (units, tenants,
        entities id+name only, templates) — available to both roles."""
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        return {
            'units': [{'id': u.id, 'code': u.code or '', 'property_id': u.property_id.id,
                       'property': u.property_id.name or '', 'status': u.status or ''}
                      for u in env['lhc.unit'].search([], order='code')],
            'tenants': [{'id': t.id, 'name': t.name or ''}
                        for t in env['lhc.tenant'].search([], order='name')],
            'entities': [{'id': e.id, 'name': e.name or '', 'gst': e.gst_applicable}
                         for e in env['lhc.billing.entity'].search([], order='name')],
            'templates': [{'id': tp.id, 'name': tp.name or ''}
                          for tp in env['lhc.agreement.template'].search([], order='name')],
        }

    @http.route('/lhc/data/agreements', type='json', auth='user')
    def lhc_agreements(self, search=None, status=None, offset=0, limit=50, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        Agr = env['lhc.agreement']
        domain = []
        term = (search or '').strip()
        if term:
            domain += ['|', '|', '|',
                       ('name', 'ilike', term),
                       ('primary_tenant_id.name', 'ilike', term),
                       ('unit_id.code', 'ilike', term),
                       ('billing_entity_id.name', 'ilike', term)]
        if status == 'archived':
            Agr = Agr.with_context(active_test=False)
            domain.append(('active', '=', False))
        elif status in ('draft', 'active', 'notice', 'expired'):
            domain.append(('state', '=', status))
        try:
            offset = max(0, int(offset)); limit = min(200, max(1, int(limit)))
        except (TypeError, ValueError):
            offset, limit = 0, 50
        total = Agr.search_count(domain)
        rows = []
        for a in Agr.search(domain, offset=offset, limit=limit, order='name desc'):
            rows.append({
                'id': a.id, 'name': a.name or '',
                'unit': a.unit_id.code or '',
                'tenant': a.primary_tenant_id.name or '',
                'entity': a.billing_entity_id.name or '',
                'gst': a.gst_applicable,
                'payable_rent': a.payable_rent,
                'end_date': a.end_date and a.end_date.strftime('%d %b %Y') or '',
                'state': a.state or 'draft',
                'archived': not a.active,
            })
        return {'agreements': rows, 'total': total, 'offset': offset, 'limit': limit}

    @http.route('/lhc/agreement/save', type='json', auth='user')
    def lhc_agreement_save(self, template_id=None, unit_id=None, tenant_id=None,
                           entity_id=None, base_rent=None, discount=None,
                           service_charge=None, start_date=None, end_date=None,
                           due_day=None, notice_period_days=None, lockin_months=None,
                           escalation_pct=None, advance_total=None, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        env = request.env
        if not unit_id:
            return {'ok': False, 'error': 'Unit is required.'}
        if not tenant_id:
            return {'ok': False, 'error': 'Primary tenant is required.'}
        if not entity_id:
            return {'ok': False, 'error': 'Billing entity is required.'}
        try:
            base = float(base_rent or 0)
        except (TypeError, ValueError):
            base = 0.0
        if base <= 0:
            return {'ok': False, 'error': 'Base rent is required.'}
        if not start_date or not end_date:
            return {'ok': False, 'error': 'Start and end dates are required.'}
        unit = env['lhc.unit'].browse(int(unit_id))
        if not unit.exists():
            return {'ok': False, 'error': 'Unit not found.'}
        tmpl = env['lhc.agreement.template'].browse(int(template_id)) if template_id else False
        if not tmpl or not tmpl.exists():
            tmpl = env['lhc.agreement.template'].search([], limit=1)
        if not tmpl:
            return {'ok': False, 'error': 'No agreement template exists — create one first.'}

        def num(v):
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0

        def intg(v, d=0):
            try:
                return int(v)
            except (TypeError, ValueError):
                return d
        vals = {
            'template_id': tmpl.id,
            'property_id': unit.property_id.id,
            'unit_id': unit.id,
            'primary_tenant_id': int(tenant_id),
            'billing_entity_id': int(entity_id),
            'due_day': intg(due_day, 10),
            'notice_period_days': intg(notice_period_days, 30),
            'lockin_months': intg(lockin_months, 0),
            'escalation_pct': num(escalation_pct) or 7.0,
            'advance_total': num(advance_total),
            'version_ids': [(0, 0, {
                'base_rent': base,
                'discount': num(discount),
                'service_charge': num(service_charge),
                'start_date': start_date,
                'end_date': end_date,
                'is_current': True,
            })],
        }
        try:
            agr = env['lhc.agreement'].create(vals)
            agr.action_confirm()
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'id': agr.id, 'name': agr.name}

    @http.route('/lhc/agreement/archive', type='json', auth='user')
    def lhc_agreement_archive(self, agreement_id=None, active=False, **kw):
        if not _is_lhc_user(request.env.user):
            raise AccessError("Not an LHC NEST user.")
        a = request.env['lhc.agreement'].with_context(active_test=False).browse(int(agreement_id or 0))
        if not a.exists():
            return {'ok': False, 'error': 'Agreement not found.'}
        a.active = bool(active)
        return {'ok': True, 'active': a.active}

    # ------------------------------------------------------------------
    # Billing Entities (Admin only) — the Lessor records printed on agreements.
    # ------------------------------------------------------------------
    @http.route('/lhc/data/entities', type='json', auth='user')
    def lhc_entities(self, **kw):
        self._require_lhc_admin()
        env = request.env
        rows = []
        for e in env['lhc.billing.entity'].search([]):
            acct = e.bank_account_no or ''
            rows.append({
                'id': e.id,
                'name': e.name or '',
                'gst_applicable': e.gst_applicable,
                'gstin': e.gstin or '',
                'pan': e.pan or '',
                'receipt_type': e.receipt_type or '',
                'bank': ((e.bank_name or '') + (' ****' + acct[-4:] if acct else '')).strip(),
                'also_receives_building': e.also_receives_building,
            })
        return {'entities': rows}

    @http.route('/lhc/entity/save', type='json', auth='user')
    def lhc_entity_save(self, name=None, relation=None, age=None, mobile=None,
                        aadhaar=None, pan=None, gst_applicable=False, gstin=None,
                        residential_address=None, bank_holder_name=None,
                        bank_account_no=None, bank_name=None, bank_branch=None,
                        bank_branch_address=None, bank_ifsc=None, entity_id=None, **kw):
        self._require_lhc_admin()
        env = request.env
        name = (name or '').strip()
        if not name:
            return {'ok': False, 'error': 'Entity name is required.'}
        gst_applicable = bool(gst_applicable)
        if gst_applicable and not (gstin or '').strip():
            return {'ok': False, 'error': 'GSTIN is required for a GST-registered entity.'}
        try:
            age_val = int(age) if age not in (None, '', False) else 0
        except (TypeError, ValueError):
            age_val = 0
        vals = {
            'name': name,
            'relation': (relation or '').strip(),
            'age': age_val,
            'mobile': (mobile or '').strip(),
            'aadhaar': (aadhaar or '').strip(),
            'pan': (pan or '').strip(),
            'gst_applicable': gst_applicable,
            'gstin': (gstin or '').strip(),
            'residential_address': (residential_address or '').strip(),
            'bank_holder_name': (bank_holder_name or '').strip(),
            'bank_account_no': (bank_account_no or '').strip(),
            'bank_name': (bank_name or '').strip(),
            'bank_branch': (bank_branch or '').strip(),
            'bank_branch_address': (bank_branch_address or '').strip(),
            'bank_ifsc': (bank_ifsc or '').strip(),
        }
        try:
            if entity_id:
                e = env['lhc.billing.entity'].browse(int(entity_id))
                if not e.exists():
                    return {'ok': False, 'error': 'Entity not found.'}
                e.write(vals)
            else:
                e = env['lhc.billing.entity'].create(vals)
        except Exception as ex:
            return {'ok': False, 'error': str(ex)}
        return {'ok': True, 'id': e.id}

    # ------------------------------------------------------------------
    # User management (Admin only) — manage LHC logins from inside the app
    # ------------------------------------------------------------------
    def _require_lhc_admin(self):
        if not request.env.user.has_group(ADMIN_GROUP):
            raise AccessError("Only LHC NEST admins can manage users.")

    @http.route('/lhc/data/users', type='json', auth='user')
    def lhc_users(self, **kw):
        self._require_lhc_admin()
        env = request.env
        admin_g = env.ref('lhc_nest.group_lhc_admin')
        acct_g = env.ref('lhc_nest.group_lhc_accountant')
        Users = env['res.users'].sudo().with_context(active_test=False)
        users = Users.search(['|',
                              ('groups_id', '=', admin_g.id),
                              ('groups_id', '=', acct_g.id)], order='name')
        rows = []
        for u in users:
            rows.append({
                'id': u.id,
                'name': u.name,
                'login': u.login,
                'role': 'admin' if u.has_group(ADMIN_GROUP) else 'accountant',
                'active': u.active,
            })
        return {'users': rows, 'self_id': env.user.id}

    @http.route('/lhc/users/save', type='json', auth='user')
    def lhc_user_save(self, name=None, login=None, password=None,
                      role='accountant', user_id=None, **kw):
        self._require_lhc_admin()
        env = request.env
        name = (name or '').strip()
        login = (login or '').strip()
        admin_g = env.ref('lhc_nest.group_lhc_admin')
        acct_g = env.ref('lhc_nest.group_lhc_accountant')
        base_g = env.ref('base.group_user')
        Users = env['res.users'].sudo()

        if not name or not login:
            return {'ok': False, 'error': 'Name and login are required.'}

        # Reset the two LHC role groups, then apply the chosen one (+ internal user)
        role_cmds = [(3, admin_g.id), (3, acct_g.id), (4, base_g.id)]
        role_cmds.append((4, admin_g.id if role == 'admin' else acct_g.id))

        if user_id:
            u = Users.browse(int(user_id))
            if not u.exists():
                return {'ok': False, 'error': 'User not found.'}
            dup = Users.with_context(active_test=False).search(
                [('login', '=', login), ('id', '!=', u.id)], limit=1)
            if dup:
                return {'ok': False, 'error': 'That login is already in use.'}
            vals = {'name': name, 'login': login}
            if password:
                vals['password'] = password
            u.write(vals)
            u.write({'groups_id': role_cmds})
            return {'ok': True, 'id': u.id}
        else:
            if not password:
                return {'ok': False, 'error': 'Password is required for a new user.'}
            dup = Users.with_context(active_test=False).search(
                [('login', '=', login)], limit=1)
            if dup:
                return {'ok': False, 'error': 'That login is already in use.'}
            u = Users.create({
                'name': name, 'login': login, 'password': password,
                'groups_id': [(6, 0, [base_g.id,
                                      admin_g.id if role == 'admin' else acct_g.id])],
            })
            return {'ok': True, 'id': u.id}

    @http.route('/lhc/users/toggle', type='json', auth='user')
    def lhc_user_toggle(self, user_id=None, **kw):
        self._require_lhc_admin()
        env = request.env
        u = env['res.users'].sudo().with_context(active_test=False).browse(int(user_id))
        if not u.exists():
            return {'ok': False, 'error': 'User not found.'}
        if u.id == env.user.id:
            return {'ok': False, 'error': "You can't deactivate yourself."}
        if u.id == env.ref('base.user_admin').id:
            return {'ok': False, 'error': "The main administrator can't be deactivated."}
        u.active = not u.active
        return {'ok': True, 'active': u.active}
