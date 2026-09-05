# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta


class LhcAgreement(models.Model):
    _name = 'lhc.agreement'
    _description = 'LHC Rental Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'lhc.inr.mixin', 'lhc.company.mixin']
    _order = 'name desc'

    name = fields.Char('Agreement No.', copy=False, readonly=True, default='New', tracking=True)
    active = fields.Boolean(default=True)  # soft delete (spec 4.6)

    template_id = fields.Many2one('lhc.agreement.template', string='Template', required=True)
    property_id = fields.Many2one('lhc.property', string='Property', required=True)
    unit_id = fields.Many2one('lhc.unit', string='Unit', required=True, tracking=True,
                              domain="[('property_id','=',property_id)]")
    primary_tenant_id = fields.Many2one('lhc.tenant', string='Primary Tenant',
                                        required=True, tracking=True)
    joint_tenant_ids = fields.One2many('lhc.joint.tenant', 'agreement_id', string='Joint Tenants')

    # Billing & bank — locked after save until unit vacant (spec 3)
    billing_entity_id = fields.Many2one('lhc.billing.entity', string='Billing Entity',
                                        required=True, tracking=True)
    gst_applicable = fields.Boolean(related='billing_entity_id.gst_applicable',
                                    string='GST Applicable', store=True)
    bank_label = fields.Char(related='billing_entity_id.bank_label', string='Bank Account')

    # Escalation preset (spec 4.2)
    escalation_pct = fields.Float('Escalation %', default=7.0)
    escalation_frequency = fields.Selection([
        ('1', '1st Renewal (every term)'),
        ('2', '2nd Renewal (skip one)'),
        ('3', '3rd Renewal (skip two)'),
    ], string='Applies Every', default='2')
    deposit_escalates = fields.Boolean('Deposit Also Escalates?')

    # Dates & terms
    due_day = fields.Integer('Due Day', default=10, help="Day of month rent is due — varies by deal.")
    notice_period_days = fields.Integer('Notice Period (days)', default=30)
    lockin_months = fields.Integer('Lock-in Period (months)', default=0,
                                   help="Termination not allowed before this many months (spec 4.2).")

    # Advance / deposit. A deposit is a term of the lease: agreed on the
    # agreement, collected in installments, settled at vacate. lhc.advance
    # .installment therefore ships with leasing, not money — putting it in money
    # would make leasing depend on money for both installment_ids here and
    # advance_held on the vacate settlement, while money already depends on
    # leasing. Its menu still sits under the Money group.
    advance_total = fields.Float('Agreed Advance / Deposit (₹)')
    installment_ids = fields.One2many('lhc.advance.installment', 'agreement_id',
                                      string='Advance Installments')
    advance_collected = fields.Float('Advance Collected', compute='_compute_advance', store=True)
    advance_balance = fields.Float('Advance Balance', compute='_compute_advance', store=True)

    agreement_notes = fields.Text('Agreement / Renewal Notes')

    version_ids = fields.One2many('lhc.agreement.version', 'agreement_id', string='Versions')
    current_version_id = fields.Many2one('lhc.agreement.version', string='Current Version',
                                         compute='_compute_current_version', store=True)
    payable_rent = fields.Float(related='current_version_id.payable_rent', string='Payable Rent',
                                store=True)
    start_date = fields.Date(related='current_version_id.start_date', string='Start', store=True)
    end_date = fields.Date(related='current_version_id.end_date', string='End Date', store=True)

    # Fixtures pulled from the unit (spec 5.1) — one record shown in two places
    fixture_ids = fields.One2many(related='unit_id.fixture_ids', string='Fixtures', readonly=True)
    photo_ids = fields.One2many('lhc.unit.photo', 'agreement_id', string='Photos')

    # Notice
    notice_date = fields.Date('Notice Date', tracking=True)
    notice_reason = fields.Char('Notice Reason')
    expected_vacate_date = fields.Date('Expected Vacate Date')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('notice', 'Notice Given'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    default_breach_text = fields.Char(related='template_id.default_breach_text',
                                      string='Default / Breach Handling')


    @api.depends('advance_total', 'installment_ids.amount')
    def _compute_advance(self):
        """Deposit collected so far, and what is still outstanding.

        Both fields declared it but the method was never written, so the
        columns stayed NULL: the agreement form, the mobile agreement detail
        and — through ``lhc.vacate.advance_held`` — the vacate settlement all
        read the deposit as zero, and any recompute raised AttributeError.
        """
        for agr in self:
            collected = sum(agr.installment_ids.mapped('amount'))
            agr.advance_collected = collected
            agr.advance_balance = (agr.advance_total or 0.0) - collected

    @api.depends('version_ids.is_current')
    def _compute_current_version(self):
        for agr in self:
            cur = agr.version_ids.filtered('is_current')[:1]
            agr.current_version_id = cur.id if cur else (agr.version_ids[:1].id if agr.version_ids else False)

    @api.onchange('property_id')
    def _onchange_property(self):
        if self.property_id and self.unit_id and self.unit_id.property_id != self.property_id:
            self.unit_id = False

    @api.onchange('template_id')
    def _onchange_template(self):
        if self.template_id and self.property_id:
            pass  # template drives clause text only; field structure unchanged

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lhc.agreement') or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        for agr in self:
            if not agr.version_ids:
                raise UserError("Add at least one rent structure (version) before confirming.")
            agr.version_ids.filtered('is_current').write({})  # ensure computed
            agr.state = 'active'
            agr.unit_id.status = 'occupied'
            if agr.primary_tenant_id and not agr.primary_tenant_id.move_in_date:
                agr.primary_tenant_id.move_in_date = agr.start_date or fields.Date.context_today(self)

    def _ensure_admin_for_renewal(self):
        """Renewal / escalation is Admin-only. An Accountant may only send a
        renewal reminder (Give Notice). Enforced server-side so the UI is not
        the only gate (role matrix)."""
        if not self.env.user.has_group('lhc_nest.group_lhc_admin'):
            raise UserError(
                "Only an Admin can renew an agreement or apply an escalation. "
                "As an Accountant you can send a renewal reminder instead.")

    def action_open_renew_wizard(self):
        self.ensure_one()
        self._ensure_admin_for_renewal()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Renew Agreement — %s' % self.name,
            'res_model': 'lhc.renew.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_agreement_id': self.id,
                'default_current_payable': self.payable_rent,
                'default_pct': self.escalation_pct,
            },
        }

    def action_open_notice_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Give Vacate Notice — %s' % self.name,
            'res_model': 'lhc.notice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_agreement_id': self.id,
                'default_notice_period_days': self.notice_period_days,
            },
        }

    # ---- Give Notice (spec 4.3) ----
    def action_give_notice(self, notice_date=None, reason=None):
        self.ensure_one()
        notice_date = notice_date or fields.Date.context_today(self)
        self.write({
            'notice_date': notice_date,
            'notice_reason': reason,
            'expected_vacate_date': fields.Date.to_date(notice_date) + relativedelta(
                days=self.notice_period_days or 0),
            'state': 'notice',
        })
        self.unit_id.status = 'notice'
        # Prepare a vacate checklist
        self.env['lhc.vacate']._prepare_for_agreement(self)
        return True

    # ---- Renewal (spec 4.2) creates a NEW version row, never edits in place ----
    def action_renew(self, method='A', base_rent=None, discount=None, service_charge=None,
                     pct=None, fixed_amount=None, reason=None):
        self.ensure_one()
        self._ensure_admin_for_renewal()
        cur = self.current_version_id
        if not cur:
            raise UserError("No current version to renew from.")
        payable = cur.payable_rent
        new_base = cur.base_rent
        new_disc = cur.discount
        new_svc = cur.service_charge
        if method == 'A':  # % on current payable
            pct = pct if pct is not None else self.escalation_pct
            new_base = round(payable * (1 + (pct or 0) / 100.0), 2)
            new_disc = 0.0
            new_svc = 0.0
        elif method == 'B':  # revised base + new discount
            new_base = base_rent if base_rent is not None else cur.base_rent
            new_disc = discount if discount is not None else 0.0
            new_svc = service_charge if service_charge is not None else 0.0
        elif method == 'C':  # fixed rupee increase on payable
            new_base = payable + (fixed_amount or 0.0)
            new_disc = 0.0
            new_svc = 0.0
        elif method == 'D':  # manual override — requires justification
            if not reason:
                raise ValidationError("Manual override (Method D) requires a justification note.")
            new_base = base_rent if base_rent is not None else cur.base_rent
            new_disc = discount if discount is not None else cur.discount
            new_svc = service_charge if service_charge is not None else cur.service_charge
        # new term dates
        start = cur.end_date or fields.Date.context_today(self)
        end = fields.Date.to_date(start) + relativedelta(months=11)
        cur.is_current = False
        self.env['lhc.agreement.version'].create({
            'agreement_id': self.id,
            'base_rent': new_base,
            'discount': new_disc,
            'service_charge': new_svc,
            'start_date': start,
            'end_date': end,
            'escalation_method': method,
            'note': reason or '',
            'is_current': True,
        })
        self.state = 'active'
        self.message_post(body="Renewed via method %s. New payable computed." % method)
        return True


class LhcAgreementVersion(models.Model):
    _name = 'lhc.agreement.version'
    _description = 'LHC Agreement Version'
    _order = 'agreement_id, sequence, id'

    agreement_id = fields.Many2one('lhc.agreement', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='agreement_id.company_id', store=True,
                                 index=True, readonly=True)
    sequence = fields.Integer('Version No.', default=1)
    is_current = fields.Boolean('Current', default=True)

    # Four separate values, never merged (spec 4.1)
    base_rent = fields.Float('Base Rent (₹)', required=True)
    discount = fields.Float('Discount (₹)')
    service_charge = fields.Float('Service Charge (₹)')
    payable_rent = fields.Float('Payable Rent (₹)', compute='_compute_payable', store=True)

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    escalation_method = fields.Selection([
        ('init', 'Initial'),
        ('A', 'A — % on current payable'),
        ('B', 'B — revised base + discount'),
        ('C', 'C — fixed rupee increase'),
        ('D', 'D — manual override'),
    ], string='Escalation Method', default='init')
    note = fields.Text('Note')

    @api.depends('base_rent', 'discount', 'service_charge')
    def _compute_payable(self):
        for v in self:
            v.payable_rent = (v.base_rent or 0.0) - (v.discount or 0.0) + (v.service_charge or 0.0)


class LhcJointTenant(models.Model):
    _name = 'lhc.joint.tenant'
    _description = 'LHC Joint Tenant'

    agreement_id = fields.Many2one('lhc.agreement', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='agreement_id.company_id', store=True,
                                 index=True, readonly=True)
    name = fields.Char('Name', required=True)
    mobile = fields.Char('Phone')
    relation = fields.Char('Relation to Primary')
    aadhaar = fields.Char('Aadhaar')
    pan = fields.Char('PAN')
    id_doc = fields.Binary('ID Document')
    id_doc_filename = fields.Char('ID Filename')
