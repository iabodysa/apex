# Copyright (c) 2026, AFMCO and contributors
"""Guards for the setup-wizard demo data and its removal.

The offer only holds if the removal is exhaustive, so the load-bearing test here is
the equal-sets one: the build declares a DocType per step, the removal walks the
shared list, and the two must cover the same set. Drop a step and the demo starts
leaving a DocType nobody clears.

The round trip proves it for real rather than on paper — every touched DocType is
counted before the build, after the build, and after the removal, and the third
count has to equal the first.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup import demo


class TestDemoDoctypeLists(FrappeTestCase):
    def test_build_and_removal_cover_the_same_doctypes(self):
        """The build's declared DocTypes and the removal's list are EQUAL SETS.

        The removal walks DEMO_DOCTYPES reversed, so anything the build creates
        outside that list would survive the clear forever."""
        built = {doctype for doctype, _step in demo._BUILD_STEPS}
        removed = set(demo.DEMO_DOCTYPES)
        self.assertEqual(
            built,
            removed,
            "build-only: {0} | removal-only: {1}".format(
                sorted(built - removed), sorted(removed - built)
            ),
        )

    def test_removal_order_is_the_build_order_reversed(self):
        self.assertEqual(
            list(reversed(demo.DEMO_DOCTYPES))[0],
            "Maintenance Request",
            "the removal must start at the leaf, not the master",
        )
        self.assertEqual(list(reversed(demo.DEMO_DOCTYPES))[-1], "Project")

    def test_create_refuses_a_doctype_the_removal_would_not_reach(self):
        """The build cannot outgrow the removal even by accident."""
        self.assertNotIn("Note", demo.DEMO_DOCTYPES)
        with self.assertRaises(frappe.ValidationError) as caught:
            demo._create("Note", {"title": "not a demo doctype"})
        self.assertIn("Note", str(caught.exception))


class TestDemoRoundTrip(FrappeTestCase):
    """Build on a site, then clear, and prove every count came back."""

    def setUp(self):
        frappe.set_user("Administrator")
        if frappe.db.exists("User", demo.DEMO_OWNER):
            demo.clear_demo_data()

    def tearDown(self):
        frappe.set_user("Administrator")
        if frappe.db.exists("User", demo.DEMO_OWNER):
            demo.clear_demo_data()

    def _counts(self):
        return {doctype: frappe.db.count(doctype) for doctype in demo.DEMO_DOCTYPES}

    def test_build_then_clear_returns_every_count_to_baseline(self):
        before = self._counts()
        demo.build_demo_data()
        built = self._counts()
        self.assertTrue(
            any(built[dt] > before[dt] for dt in demo.DEMO_DOCTYPES),
            "the build created nothing",
        )

        demo.clear_demo_data()
        after = self._counts()
        for doctype in demo.DEMO_DOCTYPES:
            self.assertEqual(
                after[doctype],
                before[doctype],
                "{0}: {1} before, {2} built, {3} after".format(
                    doctype, before[doctype], built[doctype], after[doctype]
                ),
            )

    def test_every_demo_row_carries_the_owner_key(self):
        demo.build_demo_data()
        for doctype in demo.DEMO_DOCTYPES:
            owned = frappe.db.count(doctype, {"owner": demo.DEMO_OWNER})
            self.assertGreater(owned, 0, "{0} created no owner-keyed row".format(doctype))

    def test_submitted_row_is_cancelled_so_its_reversal_fires(self):
        """A raw delete of the submitted Housing Assignment would strand its Bed on
        'Occupied'. Cancelling first is what puts the bed back."""
        demo.build_demo_data()
        assignment = frappe.get_all(
            "Housing Assignment",
            filters={"owner": demo.DEMO_OWNER},
            fields=["name", "bed", "docstatus"],
        )[0]
        self.assertEqual(assignment.docstatus, 1, "the demo must submit this row")
        self.assertEqual(frappe.db.get_value("Bed", assignment.bed, "status"), "Occupied")

        bed = assignment.bed
        demo.clear_demo_data()
        # The bed went with the demo; what matters is that no bed anywhere is left
        # pointing at a demo assignment that no longer exists.
        self.assertFalse(frappe.db.exists("Bed", bed))
        self.assertFalse(frappe.db.exists("Housing Assignment", assignment.name))

    def test_boot_flag_is_set_by_the_build_and_cleared_by_the_removal(self):
        boot = frappe._dict()
        demo.boot_demo(boot)
        self.assertFalse(boot.apex_demo_data)

        demo.build_demo_data()
        boot = frappe._dict()
        demo.boot_demo(boot)
        self.assertTrue(boot.apex_demo_data)

        demo.clear_demo_data()
        boot = frappe._dict()
        demo.boot_demo(boot)
        self.assertFalse(boot.apex_demo_data)

    def test_removal_refuses_when_there_is_no_demo_user(self):
        """Without the owner key there is no safe filter, so it must refuse rather
        than fall back to a broader sweep."""
        self.assertFalse(frappe.db.exists("User", demo.DEMO_OWNER))
        with self.assertRaises(frappe.ValidationError):
            demo.clear_demo_data()

    def test_removal_deletes_the_demo_users_and_their_user_permissions(self):
        demo.build_demo_data()
        self.assertTrue(
            frappe.db.exists(
                "User Permission", {"user": demo.DEMO_SUPERVISOR, "allow": "Building"}
            )
        )
        demo.clear_demo_data()
        for user in demo.DEMO_USERS:
            self.assertFalse(frappe.db.exists("User", user))
            self.assertFalse(frappe.db.exists("User Permission", {"user": user}))

    def test_a_second_build_is_a_no_op(self):
        demo.build_demo_data()
        counts = self._counts()
        demo.build_demo_data()
        self.assertEqual(self._counts(), counts)


class TestDemoWizardArg(FrappeTestCase):
    def test_unticked_box_enqueues_nothing(self):
        calls = []
        original = frappe.enqueue
        frappe.enqueue = lambda *a, **kw: calls.append((a, kw))
        try:
            demo.setup_demo({})
            demo.setup_demo(None)
            self.assertEqual(calls, [])
            demo.setup_demo({demo.DEMO_ARG: 1})
        finally:
            frappe.enqueue = original
        self.assertEqual(len(calls), 1)
        self.assertTrue(
            calls[0][1].get("enqueue_after_commit"),
            "the build must be queued after commit so it cannot fail setup",
        )

    def test_arg_is_not_erpnexts_setup_demo(self):
        """Sharing ERPNext's fieldname would build an ERPNext demo company off one
        tick of the Apex box (erpnext/setup/setup_wizard/setup_wizard.py:68)."""
        self.assertNotEqual(demo.DEMO_ARG, "setup_demo")


class TestCompanyDataToBeIgnored(FrappeTestCase):
    def test_declared_doctypes_are_submittable_and_carry_a_company_link(self):
        """Both consumers of this hook require it. ERPNext filters DocFields whose
        options are Company; HRMS's Company on_trash handler queries each declared
        DocType BY its company field, so one without that field raises there."""
        declared = frappe.get_hooks("company_data_to_be_ignored", app_name="apex")
        self.assertTrue(declared)
        for doctype in declared:
            meta = frappe.get_meta(doctype)
            self.assertTrue(meta.is_submittable, "{0} is not submittable".format(doctype))
            field = meta.get_field("company")
            self.assertIsNotNone(field, "{0} has no company field".format(doctype))
            self.assertEqual(field.fieldtype, "Link")
            self.assertEqual(field.options, "Company")

    def test_declaration_reaches_the_erpnext_ignore_list(self):
        from erpnext.setup.doctype.transaction_deletion_record.transaction_deletion_record import (
            get_doctypes_to_be_ignored,
        )

        ignored = set(get_doctypes_to_be_ignored())
        for doctype in frappe.get_hooks("company_data_to_be_ignored", app_name="apex"):
            self.assertIn(doctype, ignored)


if __name__ == "__main__":
    unittest.main()
