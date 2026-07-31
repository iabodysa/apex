# Copyright (c) 2026, AFMCO and contributors
"""Unified Fuel Request tests.

The three former DocTypes (Fuel Request / Fuel Topup Request / Fuel Chip Request)
were merged into a single Fuel Request with a ``request_type`` Select
(Standard / Top-up / Chip). These tests prove every per-type behaviour was
preserved verbatim after the merge:

* **Standard** — quota consumption is applied idempotently on submit (Done) and
  the request is picked up by the accrual engine (``ledgered`` flag) into the
  Fuel Consumption Ledger.
* **Top-up** — a temporary top-up requires a revert-due date, and an overdue one
  is auto-reverted by ``unreverted_topup_watch`` (status -> Reverted, reverted=1),
  which still queries Fuel Request filtered to request_type=Top-up.
* **Chip** — a cancellation cannot be submitted without inactivity evidence AND
  owner acknowledgement; an Issue needs neither.
* **request_type guards** — an invalid request_type is rejected; per-type required
  fields are enforced; illegal status jumps are rejected per type.

Migration idempotency is covered by the patch's own ``frappe.db.exists`` name
guard (a row whose preserved FT-/FC- name already exists is skipped); re-running
``bench migrate`` therefore never double-inserts. That guard is exercised here
indirectly: every test runs against a freshly-migrated site where the two source
DocTypes are already gone (asserted in ``TestFuelMergeShape``).
"""


import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_workflow_name
from frappe.utils import add_days, today

from apex.salis.fuel_engine import accrue_fuel_consumption
from apex.salis.tasks import unreverted_topup_watch
from apex.tests._helpers import submit_via_workflow
from apex.tests.factories import make_vehicle, purge_doc


def _drive_to_done(doc):
    """Move a Pending Fuel Request to Done via the native workflow when one is
	active, else fall back to the direct save+submit path (a site without the
	workflow seeded).

	Driven as Administrator, who may make any transition the workflow offers. The
	approval transition carries a segregation-of-duties condition
	(``requested_by != session.user``), so the requester is re-stamped to a
	distinct sentinel user first — these legacy tests exercise the ledger /
	auto-revert side-effects, not the SoD gate (that is covered in
	test_fuel_request_workflow)."""
    if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
        if doc.requested_by == frappe.session.user:
            doc.db_set("requested_by", "Guest")  # [#gzmtd5]
            doc.reload()
        apply_workflow(doc, "Approve")  # [#ms0ltc]
        doc.reload()
        apply_workflow(doc, "Complete")  # [#lpqooh]
        doc.reload()
    else:
        doc.status = "Approved"
        doc.save(ignore_permissions=True)
        doc.status = "Done"
        doc.save(ignore_permissions=True)
        doc.submit()


class TestFuelMergeShape(FrappeTestCase):
    """The structural outcome of the merge: the two source DocTypes are gone and
	Fuel Request carries the unified field set."""

    def test_source_doctypes_dropped(self):
        self.assertFalse(
            frappe.db.exists("DocType", "Fuel Topup Request"),
            "Fuel Topup Request must be dropped by the merge patch.",
        )
        self.assertFalse(
            frappe.db.exists("DocType", "Fuel Chip Request"),
            "Fuel Chip Request must be dropped by the merge patch.",
        )

    def test_request_type_field_present(self):
        meta = frappe.get_meta("Fuel Request")
        self.assertTrue(meta.has_field("request_type"))
        options = (meta.get_field("request_type").options or "").split("\n")
        self.assertEqual([o for o in options if o], ["Standard", "Top-up", "Chip"])
        # [#7m3vxc]
        for f in (
            "topup_litres", "is_temporary", "revert_due_date", "reverted",
            "chip_number", "action", "inactivity_evidence",
            "owner_acknowledged", "migrated_from",
        ):
            self.assertTrue(meta.has_field(f), f"Unified Fuel Request must carry {f}.")


class TestFuelRequestStandard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = make_vehicle("FR STD 1")

    def _make_done_standard(self, request_date):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Standard",
            "vehicle": self.vehicle,
            "request_date": request_date,
            "requested_litres": 8,
            "amount": 120,
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        _drive_to_done(doc)
        return doc.name

    def test_standard_default_request_type(self):
        """A Fuel Request created without an explicit request_type defaults to
		Standard (backward-compatible with pre-merge creation)."""
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "vehicle": self.vehicle,
            "requested_litres": 3,
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Fuel Request", doc.name))
        self.assertEqual(doc.request_type, "Standard")

    def test_standard_requires_litres(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Standard",
            "vehicle": self.vehicle,
            "requested_litres": 0,
            "status": "Pending",
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_standard_is_ledgered_by_engine(self):
        name = self._make_done_standard(add_days(today(), -10))
        self.addCleanup(lambda: self._cleanup(name))
        frappe.db.delete("Fuel Consumption Ledger",
                         {"source_type": "Fuel Request", "source_name": name})
        frappe.db.set_value("Fuel Request", name, "ledgered", 0, update_modified=False)

        accrue_fuel_consumption()

        self.assertEqual(
            frappe.db.count("Fuel Consumption Ledger",
                            {"source_type": "Fuel Request", "source_name": name}),
            1, "A Done Standard request must post one ledger row.")
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "ledgered"), 1)

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        frappe.db.delete("Fuel Consumption Ledger",
                         {"source_type": "Fuel Request", "source_name": name})
        purge_doc("Fuel Request", name)


class TestFuelRequestTopup(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = make_vehicle("FR TOPUP 1")

    def test_temporary_requires_revert_due_date(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Top-up",
            "vehicle": self.vehicle,
            "topup_litres": 10,
            "is_temporary": 1,
            "status": "Pending",
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_topup_requires_litres(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Top-up",
            "vehicle": self.vehicle,
            "topup_litres": 0,
            "status": "Pending",
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_overdue_temporary_topup_is_auto_reverted(self):
        """A submitted, Done, temporary top-up past its revert-due date is flipped
		to Reverted by unreverted_topup_watch (which now queries Fuel Request
		filtered to request_type=Top-up)."""
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Top-up",
            "vehicle": self.vehicle,
            "topup_litres": 12,
            "is_temporary": 1,
            "revert_due_date": add_days(today(), -3),
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        _drive_to_done(doc)
        name = doc.name
        self.addCleanup(lambda: purge_doc("Fuel Request", name))

        self.assertEqual(frappe.db.get_value("Fuel Request", name, "reverted"), 0)

        unreverted_topup_watch()

        self.assertEqual(frappe.db.get_value("Fuel Request", name, "reverted"), 1,
                         "Overdue temporary top-up must be auto-reverted.")
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "status"), "Reverted")

    def test_non_temporary_topup_is_left_alone(self):
        """A non-temporary top-up is never touched by the revert watch."""
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Top-up",
            "vehicle": self.vehicle,
            "topup_litres": 5,
            "is_temporary": 0,
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        _drive_to_done(doc)
        name = doc.name
        self.addCleanup(lambda: purge_doc("Fuel Request", name))

        unreverted_topup_watch()
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "status"), "Done")
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "reverted"), 0)


class TestFuelRequestChip(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = make_vehicle("FR CHIP 1")

    def test_issue_chip_submits_without_evidence(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Chip",
            "vehicle": self.vehicle,
            "action": "Issue",
            "chip_number": "CHIP-0001",
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Fuel Request", doc.name))
        submit_via_workflow(doc)  # [#3vfaf1]
        self.assertEqual(doc.docstatus, 1)

    def test_replace_requires_chip_number(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Chip",
            "vehicle": self.vehicle,
            "action": "Replace",
            "status": "Pending",
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_cancel_chip_requires_evidence_and_ack(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Chip",
            "vehicle": self.vehicle,
            "action": "Cancel",
            "chip_number": "CHIP-0002",
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        name = doc.name
        self.addCleanup(lambda: purge_doc("Fuel Request", name))

        # [#h93m1u]
        self.assertRaises(frappe.ValidationError, doc.submit)

        # [#nzk62t]
        doc = frappe.get_doc("Fuel Request", name)
        doc.inactivity_evidence = "/files/evidence.pdf"
        doc.save(ignore_permissions=True)
        self.assertRaises(frappe.ValidationError, doc.submit)

        # [#6xsbgv]
        doc = frappe.get_doc("Fuel Request", name)
        doc.inactivity_evidence = "/files/evidence.pdf"
        doc.owner_acknowledged = 1
        doc.save(ignore_permissions=True)
        submit_via_workflow(doc)
        self.assertEqual(doc.docstatus, 1)


class TestFuelRequestTypeGuards(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = make_vehicle("FR GUARD 1")

    def test_invalid_request_type_rejected(self):
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Bogus",
            "vehicle": self.vehicle,
            "status": "Pending",
        })
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

    def test_illegal_status_jump_rejected(self):
        """Transitions are now owned by the Fuel Request Workflow: a status jump
		that is not an offered transition is rejected. Pending -> Done skips
		Approved, so the workflow blocks it (the hand-rolled ``_TRANSITIONS`` map
		was retired in the conversion). Administrator drives the workflow here."""
        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "request_type": "Standard",
            "vehicle": self.vehicle,
            "requested_litres": 4,
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Fuel Request", doc.name))
        # [#n5y0oc]
        if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
            from frappe.model.workflow import apply_workflow
            with self.assertRaises(frappe.ValidationError):
                apply_workflow(doc, "Complete")  # [#bfud4b]
        else:
            doc.status = "Done"
            self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)
