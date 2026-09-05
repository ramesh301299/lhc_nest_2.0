# -*- coding: utf-8 -*-
"""The foundation loaded, and the things every other addon reaches for exist.

Every LHC NEST addon depends on this one and none of them can be installed
without it. When lhc_nest is missing or half-loaded the failure surfaces as an
unrelated error deep inside whichever addon happened to load first, so the
handful of names the others actually import are asserted here instead.
"""
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "lhc", "lhc_nest")
class TestLhcNestInstall(TransactionCase):

    def test_shared_models_present(self):
        """The mixins and the entity model are in the registry."""
        for model in ("lhc.billing.entity", "lhc.company.mixin", "lhc.inr.mixin"):
            self.assertIn(model, self.env.registry,
                          "%s is missing — dependent addons inherit it" % model)

    def test_menu_skeleton_present(self):
        """The root and the five group headers the business addons hang from."""
        for xmlid in (
            "lhc_nest.menu_lhc_root",
            "lhc_nest.menu_lhc_quick",
            "lhc_nest.menu_lhc_property_grp",
            "lhc_nest.menu_lhc_leasing_grp",
            "lhc_nest.menu_lhc_money_grp",
            "lhc_nest.menu_lhc_reports_grp",
            "lhc_nest.menu_lhc_tools_grp",
        ):
            self.assertTrue(self.env.ref(xmlid, raise_if_not_found=False),
                            "%s is missing — leaf menus reference it as parent" % xmlid)

    def test_gst_is_entity_driven(self):
        """calculate_billing reads the entity flag and nothing else."""
        from odoo.addons.lhc_nest.models.billing_entity import calculate_billing

        Entity = self.env["lhc.billing.entity"]
        gst = Entity.create({"name": "T GST", "gst_applicable": True})
        plain = Entity.create({"name": "T Plain", "gst_applicable": False})

        with_gst = calculate_billing(self.env, 10000.0, gst)
        self.assertTrue(with_gst["gst_applicable"])
        self.assertEqual(with_gst["gst_amount"], 1800.0)
        self.assertEqual(with_gst["total"], 11800.0)

        without = calculate_billing(self.env, 10000.0, plain)
        self.assertFalse(without["gst_applicable"])
        self.assertEqual(without["gst_amount"], 0.0)
        self.assertEqual(without["total"], 10000.0)

    def test_maintenance_is_never_gst_marked_up(self):
        """Maintenance recovery is added as-is, outside the taxable base."""
        from odoo.addons.lhc_nest.models.billing_entity import calculate_billing

        gst = self.env["lhc.billing.entity"].create({
            "name": "T GST 2", "gst_applicable": True})
        res = calculate_billing(self.env, 10000.0, gst, maintenance_charge=500.0)
        self.assertEqual(res["taxable"], 10000.0)
        self.assertEqual(res["gst_amount"], 1800.0, "GST must not be charged on maintenance")
        self.assertEqual(res["total"], 12300.0)

    def test_inr_grouping_is_indian(self):
        """₹1,84,500 — lakh grouping, not the thousands grouping.

        Called on the abstract model itself: lhc.billing.entity does not
        inherit the mixin, the printed documents in leasing and money do.
        """
        inr = self.env["lhc.inr.mixin"].inr
        self.assertEqual(inr(184500), "₹1,84,500")
        self.assertEqual(inr(-2500), "- ₹2,500")
        self.assertEqual(inr(0), "₹0")
