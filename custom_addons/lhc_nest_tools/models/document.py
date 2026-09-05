# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LhcDocument(models.Model):
    """Backs the Documents screen — "Agreements, ID proofs, deposit receipts".

    The screen shows one row per file: Category | File | Linked To | Uploaded,
    with a download action. "Linked To" holds either a unit ("A-101") or a
    person ("Ravi Shankar"), so the link is polymorphic in the UI.

    It is modelled as four explicit Many2one fields rather than one
    ``fields.Reference``. A Reference stores "model,id" in a Char, which cannot
    be joined, cannot be grouped by in a meaningful way, and forces every API
    consumer to parse a string. Explicit relations give real foreign keys that
    the mobile API can read directly and that Odoo can search and group on —
    while ``linked_to`` still renders the single column the screen expects.
    """
    _name = 'lhc.document'
    _description = 'LHC Document'
    _inherit = ['mail.thread', 'lhc.company.mixin']
    _order = 'upload_date desc, id desc'

    name = fields.Char('Title', required=True, tracking=True)
    active = fields.Boolean(default=True)

    category = fields.Selection([
        ('agreement', 'Agreement'),
        ('id_proof', 'ID Proof'),
        ('deposit_receipt', 'Deposit Receipt'),
        ('other', 'Other'),
    ], string='Category', required=True, default='agreement', tracking=True)

    # attachment=True keeps the bytes in the filestore (ir.attachment) instead
    # of a bytea column, so the database stays small and Odoo's own
    # download/permission handling applies.
    file = fields.Binary('File', attachment=True, required=True)
    file_name = fields.Char('File Name')

    # ---- Linked To -------------------------------------------------------
    # ondelete='cascade': a document about a deleted tenant has nothing left to
    # describe, and leaving it orphaned would show a blank "Linked To" row.
    tenant_id = fields.Many2one('lhc.tenant', string='Tenant',
                                ondelete='cascade', index=True)
    unit_id = fields.Many2one('lhc.unit', string='Unit',
                              ondelete='cascade', index=True)
    agreement_id = fields.Many2one('lhc.agreement', string='Agreement',
                                   ondelete='cascade', index=True)
    property_id = fields.Many2one('lhc.property', string='Property',
                                  ondelete='cascade', index=True)
    linked_to = fields.Char('Linked To', compute='_compute_linked_to', store=True,
                            help="Single-column rendering of whichever record "
                                 "this document is attached to.")

    upload_date = fields.Date('Uploaded', default=fields.Date.context_today,
                              readonly=True)
    uploaded_by = fields.Many2one('res.users', string='Uploaded By', readonly=True,
                                  default=lambda self: self.env.user)
    note = fields.Text('Note')

    @api.depends('agreement_id', 'unit_id', 'tenant_id', 'property_id',
                 'agreement_id.name', 'unit_id.code', 'tenant_id.name',
                 'property_id.name')
    def _compute_linked_to(self):
        """Show the most specific link, matching the screen's single column."""
        for doc in self:
            if doc.agreement_id:
                doc.linked_to = doc.agreement_id.display_name
            elif doc.unit_id:
                doc.linked_to = doc.unit_id.code
            elif doc.tenant_id:
                doc.linked_to = doc.tenant_id.name
            elif doc.property_id:
                doc.linked_to = doc.property_id.name
            else:
                doc.linked_to = False

    # `category` is watched even though it is not part of the check. Odoo only
    # runs a constraint when one of its watched fields appears in the values
    # being written, so a create() that simply omits all four link fields would
    # skip the check entirely. `category` is required, so it is present in every
    # create — which makes this constraint fire on creation as well as on edit.
    @api.constrains('tenant_id', 'unit_id', 'agreement_id', 'property_id', 'category')
    def _check_has_link(self):
        """A document must belong to something.

        Without this an upload can land nowhere and become invisible on every
        record it was meant to support, while still occupying the filestore.
        """
        for doc in self:
            if not (doc.tenant_id or doc.unit_id or doc.agreement_id or doc.property_id):
                raise ValidationError(_(
                    "Link the document to a tenant, unit, agreement or property."))

    @api.onchange('file_name')
    def _onchange_file_name(self):
        """Default the title to the uploaded file's name, as the screen shows."""
        if self.file_name and not self.name:
            self.name = self.file_name
