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
        """Every DocType the build's step map declares is reachable by the removal.

        The removal walks DEMO_DOCTYPES reversed, so anything the build creates
        outside that list would survive the clear forever -- that is the build-only
        direction, and it must be empty. ``File`` is a legitimate removal-only entry:
        the Vehicle Damage Write-Off step attaches one evidence File as a byproduct
        (apex_core/setup/demo.py:_build_vehicle_write_off) with no ``_BUILD_STEPS``
        tuple of its own, so DEMO_DOCTYPES covers it for removal without a matching
        build key. A new removal-only entry beyond that pins to the same reasoning
        or the ratchet below must widen with the reason recorded here."""
        built = {doctype for doctype, _step in demo._BUILD_STEPS}
        removed = set(demo.DEMO_DOCTYPES)
        self.assertEqual(
            built - removed,
            set(),
            "the build creates a DocType the removal never scans, so it would "
            "survive the clear forever: {0}".format(sorted(built - removed)),
        )
        self.assertEqual(
            removed - built,
            {"File"},
            "a removal-only DocType appeared that is not the known File byproduct; "
            "confirm it is a real step byproduct before widening this set",
        )

    def test_removal_order_is_the_build_order_reversed(self):
        self.assertEqual(
            list(reversed(demo.DEMO_DOCTYPES))[0],
            "Rental Settlement",
            "the removal must start at the leaf, not the master",
        )
        self.assertEqual(list(reversed(demo.DEMO_DOCTYPES))[-1], "Company")

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
        self._purge()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._purge()

    def _purge(self):
        """Leave the site with no demo user and no row any demo user owns.

        ``clear_demo_data`` is the product path and is tried first, but it cannot be the
        whole cleanup here: it refuses outright when the demo user is absent, and it skips
        the users while any row survives, so one blocked row leaves the next test starting
        against a half-built site. ``_create_demo_users`` COMMITS, so that state outlives
        the per-test rollback and the next build correctly returns ``already built`` —
        which reads as a failure of the build rather than of the cleanup.

        Rows first, users second. The demo user IS the removal key
        (apex_core/setup/demo.py:309-318), so deleting it while rows remain strands every
        one of them where nothing can select them again.
        """
        if frappe.db.exists("User", demo.DEMO_OWNER):
            try:
                demo.clear_demo_data()
            except Exception:
                frappe.clear_last_message()

        owned = {"owner": ["in", list(demo.DEMO_USERS)]}
        for doctype in reversed(demo.DEMO_DOCTYPES):
            for name in frappe.get_all(doctype, filters=owned, pluck="name"):
                doc = frappe.get_doc(doctype, name)
                if doc.docstatus == 1:
                    if doc.meta.has_field("cancellation_reason") and not doc.get(
                        "cancellation_reason"
                    ):
                        doc.cancellation_reason = "demo test cleanup"
                    doc.cancel()
                frappe.delete_doc(
                    doctype,
                    name,
                    ignore_permissions=True,
                    delete_permanently=True,
                    force=True,
                )

        for user in demo.DEMO_USERS:
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, ignore_permissions=True, force=True)
        frappe.db.commit()

    def _counts(self):
        return {doctype: frappe.db.count(doctype) for doctype in demo.DEMO_DOCTYPES}

    def test_build_then_clear_returns_every_count_to_baseline(self):
        before = self._counts()
        verdict = demo.build_demo_data()
        built = self._counts()
        # Asserted before the counts, because a step failure rolls the scenario back and
        # reports out of band: without the verdict every failure arrives as "created
        # nothing" and the step that stopped it is only in an Error Log this rollback ate.
        self.assertTrue(verdict["built"], f"the build stopped at {verdict['stopped_at']}")
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
        """A raw delete of a submitted, still-occupying Housing Assignment would
        strand its Bed on 'Occupied'. Cancelling first is what puts the bed back.

        The build submits three linked Housing Assignments and, later in the same
        run, submits a Housing Checkout that deliberately releases one of them
        (apex_core/setup/demo.py:_build_checkout) -- so an unordered "grab any
        submitted row" pick can land on the one row whose Bed is correctly
        'Available' again. Excluding whatever a submitted checkout already
        released is what makes the pick land on a row still occupying its bed.
        """
        demo.build_demo_data()
        assignments = frappe.get_all(
            "Housing Assignment",
            filters={"owner": demo.DEMO_OWNER, "docstatus": 1},
            fields=["name", "bed"],
        )
        self.assertTrue(assignments, "the demo must submit at least one Housing Assignment")
        checked_out = set(
            frappe.get_all(
                "Housing Checkout",
                filters={"owner": demo.DEMO_OWNER, "docstatus": 1},
                pluck="assignment",
            )
        )
        still_occupying = [row for row in assignments if row.name not in checked_out]
        self.assertTrue(
            still_occupying, "the demo must leave at least one assignment occupying its bed"
        )
        assignment = still_occupying[0]
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
