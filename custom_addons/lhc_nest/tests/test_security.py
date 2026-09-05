# -*- coding: utf-8 -*-
"""Access-matrix tests for the foundation layer.

Asserted rather than checked by eye: an Accountant must be an internal user
who cannot reach Billing Entities, an Admin must hold the Accountant role
implicitly, and the entity model must stay company-scoped.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "lhc", "lhc_nest", "lhc_security")
class TestLhcNestAccessMatrix(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="lhc_nest_admin", groups="lhc_nest.group_lhc_admin")
        cls.accountant = new_test_user(
            cls.env, login="lhc_nest_acct", groups="lhc_nest.group_lhc_accountant")

    def test_accountant_is_an_internal_user(self):
        """Without base.group_user the backend is unreachable for the role."""
        self.assertTrue(self.accountant.has_group("base.group_user"))
        self.assertTrue(self.admin.has_group("base.group_user"))

    def test_admin_implies_accountant(self):
        """One grant, not two — menu security is written for Accountant only."""
        self.assertTrue(self.admin.has_group("lhc_nest.group_lhc_accountant"))
        self.assertFalse(self.accountant.has_group("lhc_nest.group_lhc_admin"))

    def test_role_token(self):
        """The token the web app and the Flutter app both switch on."""
        self.assertEqual(self.admin._lhc_role(), "admin")
        self.assertEqual(self.accountant._lhc_role(), "accountant")

    @mute_logger("odoo.addons.base.models.ir_model")
    def test_billing_entity_is_admin_only(self):
        """GST applicability is an admin-owned fact; an accountant cannot read it."""
        entity = self.env["lhc.billing.entity"].create({"name": "Scoped Entity"})
        self.assertTrue(entity.with_user(self.admin).read(["name"]))
        with self.assertRaises(AccessError):
            entity.with_user(self.accountant).read(["name"])

    def test_billing_entity_is_company_scoped(self):
        """The global multi-company rule is loaded and applies to the model."""
        rule = self.env.ref("lhc_nest.rule_lhc_billing_entity_company")
        # "global" is a Python keyword, so ir.rule's field of that name is only
        # reachable by subscript, never as an attribute.
        self.assertTrue(rule["global"])
        self.assertEqual(rule.model_id.model, "lhc.billing.entity")

    def test_company_id_is_required(self):
        """A record with no company is visible from every company."""
        field = self.env["lhc.billing.entity"]._fields["company_id"]
        self.assertTrue(field.required)
