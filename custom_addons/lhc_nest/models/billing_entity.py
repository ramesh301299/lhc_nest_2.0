# -*- coding: utf-8 -*-
from odoo import api, fields, models


def get_gst_rate(env):
    """Single configurable GST rate (percent). Default 18%."""
    val = env['ir.config_parameter'].sudo().get_param('lhc_nest.gst_rate', '18')
    try:
        return float(val)
    except (TypeError, ValueError):
        return 18.0


def calculate_billing(env, rent_amount, entity, maintenance_charge=0.0):
    """SINGLE SOURCE OF TRUTH for GST (spec 5.12).

    Every place that touches GST must call this instead of computing x18%
    locally. Backed by the entity's gst_applicable flag only — never derived
    from bank account, unit, property or tenant.

    Returns dict: taxable, gst_amount, maintenance, total.
    Maintenance recovery is added as-is, never GST-marked-up (spec 5.6).
    """
    rent_amount = rent_amount or 0.0
    maintenance_charge = maintenance_charge or 0.0
    gst_applicable = bool(entity) and entity.gst_applicable
    if gst_applicable:
        gst_amount = round(rent_amount * get_gst_rate(env) / 100.0, 2)
    else:
        gst_amount = 0.0
    total = rent_amount + gst_amount + maintenance_charge
    return {
        'taxable': rent_amount,
        'gst_amount': gst_amount,
        'maintenance': maintenance_charge,
        'total': total,
        'gst_applicable': gst_applicable,
    }


class LhcBillingEntity(models.Model):
    _name = 'lhc.billing.entity'
    _description = 'LHC Billing Entity (Landlord)'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'name'

    name = fields.Char('Entity Name', required=True, tracking=True)
    active = fields.Boolean(default=True)

    # GST — the ONLY driver of GST applicability
    gst_applicable = fields.Boolean('GST Registered', tracking=True,
                                    help="If set, this entity issues GST Tax Invoices. "
                                         "GST is never derived from bank/unit/tenant — only from here.")
    gstin = fields.Char('GSTIN')
    receipt_type = fields.Char('Receipt Type', compute='_compute_receipt_type', store=True)

    # Legal / agreement details (Lessor block — spec 5.9)
    relation = fields.Char('Relation (S/o or W/o)')
    age = fields.Integer('Age')
    aadhaar = fields.Char('Aadhaar No.')
    pan = fields.Char('PAN')
    mobile = fields.Char('Mobile')
    residential_address = fields.Text('Residential Address')

    # Full bank block printed verbatim on agreements
    bank_holder_name = fields.Char('Account Holder Name')
    bank_account_no = fields.Char('Account Number')
    bank_name = fields.Char('Bank Name')
    bank_branch = fields.Char('Branch Name')
    bank_branch_address = fields.Char('Branch Address')
    bank_ifsc = fields.Char('IFSC')
    bank_label = fields.Char('Bank Label', compute='_compute_bank_label', store=True,
                             help="Short label e.g. SBI ****4821")

    also_receives_building = fields.Boolean(
        'Receives All Building-level Expenses', tracking=True,
        help="Spec §5.3 — the GST entity (Soundarajan Kumar) receives ALL "
             "building-level expense postings regardless of which entity collects rent.")

    @api.depends('gst_applicable')
    def _compute_receipt_type(self):
        for rec in self:
            rec.receipt_type = 'GST Tax Invoice' if rec.gst_applicable else 'Non-GST Rent Receipt'

    @api.depends('bank_name', 'bank_account_no')
    def _compute_bank_label(self):
        for rec in self:
            if rec.bank_name and rec.bank_account_no:
                rec.bank_label = "%s ****%s" % (rec.bank_name, rec.bank_account_no[-4:])
            else:
                rec.bank_label = rec.bank_name or ''

    @api.model
    def building_expense_entity(self):
        """The entity that receives all building-level expenses."""
        entity = self.search([('also_receives_building', '=', True)], limit=1)
        if not entity:
            entity = self.search([('gst_applicable', '=', True)], limit=1)
        return entity
