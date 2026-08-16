# Copyright (c) 2026, AFMCO and contributors
"""Lease core lifecycle: creation/validation, the payment-schedule generator, what a
refused schedule regeneration must not cost the rest of the request, and that every
status the Workflow can be driven into (including the scheduler's own Expired write)
is one the Workflow itself knows about."""
import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]



class TestAccommodationLease(FrappeTestCase):

    def test_create_valid_lease(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 8000,
            "first_payment_date": "2026-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.rent_amount, 8000)
        frappe.delete_doc("Lease", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_date_raises(self):
        from apex.habitat.doctype.lease.lease import validate

        doc = frappe.get_doc({
            "doctype": "Lease",
            "building": "QA-BLDG",
            "lease_start_date": "2026-06-01",
            "lease_end_date": "2026-05-01",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_schedule_rows_default_unpaid(self):
        """Generated schedule rows are stamped 'Unpaid', never 'Paid'. The
        'Generate Payment' button selects the next non-Paid row, so a fresh row
        must read Unpaid for that selection to land on it (guards the row-pick
        contract the form button depends on)."""
        from apex.habitat.doctype.lease.lease import _build_schedule

        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-06-30",
            "rent_amount": 4000,
            "first_payment_date": "2026-01-01",
            "billing_cycle": "Monthly",
        })
        _build_schedule(doc)
        self.assertTrue(doc.payment_schedule)
        self.assertTrue(all(r.status == "Unpaid" for r in doc.payment_schedule))


class TestRegenerateScheduleFailure(FrappeTestCase):
    """What a REFUSED ``regenerate_schedule`` costs the rest of the request.

    The endpoint must not wrap its ``doc.save()`` in ``except Exception:
    frappe.db.rollback(); frappe.throw(generic)``: ``frappe.db.rollback()`` takes no
    savepoint, so it would discard the WHOLE request transaction — every row written
    before this endpoint was reached, not just the lease — and report "Could not
    save changes" in place of the validation error that actually refused the save.

    The refusal below is real, not injected: an existing lease is widened into an
    overlap with ``frappe.db.set_value`` (which skips validate), which is how live
    data drifts underneath a draft somebody left open.
    """

    def _hash(self):
        return frappe.generate_hash(length=12).upper()

    def _witness_row(self):
        """A Site row: one mandatory Data field, no links, untouched by anything else
        here, so its survival isolates the transaction behaviour."""
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A333-LEASE-" + self._hash(),
        }).insert(ignore_permissions=True).name

    def _building(self):
        return frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._hash(), "total_capacity": 4,
        }).insert(ignore_permissions=True).name

    def _draft_lease(self, building, start, end):
        return frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": building,
            "lease_start_date": start,
            "lease_end_date": end,
            "rent_amount": 6000,
            "billing_cycle": "Monthly",
            "first_payment_date": start,
        }).insert(ignore_permissions=True)

    def test_a_refused_regeneration_keeps_rows_written_earlier_in_the_same_request(self):
        from apex.habitat.doctype.lease.lease import regenerate_schedule

        witness = self._witness_row()
        building = self._building()
        lease = self._draft_lease(building, "2026-01-01", "2026-12-31")
        rival = self._draft_lease(building, "2027-01-01", "2027-12-31")
        frappe.db.set_value("Lease", rival.name, "lease_start_date", "2026-06-01")

        with self.assertRaises(frappe.ValidationError) as caught:
            regenerate_schedule(lease.name)

        self.assertIn(
            rival.name, str(caught.exception),
            "the caller must be told WHICH lease overlaps, not a generic 'could not "
            "save changes' standing in for it",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a refused regeneration must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Lease", rival.name),
            "the overlapping lease that caused the refusal must survive it",
        )


WORKFLOW = "Lease Workflow"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestTheWorkflowOwnsEveryStatusItIsGiven(FrappeTestCase):
    """the scheduler must not write a status the Workflow cannot validate.

    `status` on Lease is the Workflow's state field, and the Lease Workflow knows four
    states: Draft, Pending Approval, Approved, Rejected. The Select allows three more —
    Active, Expired, Terminated — and `lease_expiry_watchlist` writes Expired straight to
    the database. The document then sits in a value its own state machine does not contain.

    The failing sequence the card names is the first test here: approve a lease, backdate
    its end date, run the job, then open and save it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "LS " + _h()}
        ).insert(ignore_permissions=True).name

    def _building(self):
        doc = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "LS " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _drop_lease(self, name):
        """A submitted record refuses deletion, so the fixture cancels first. `db_set`
        clears the docstatus without asking the Workflow for a cancel transition it has
        no action for."""
        frappe.db.set_value("Lease", name, "docstatus", 0, update_modified=False)
        frappe.delete_doc("Lease", name, force=True, ignore_permissions=True)

    def _expired_lease(self):
        doc = frappe.get_doc(
            {
                "doctype": "Lease",
                "building": self._building(),
                "lease_start_date": add_days(today(), -60),
                "lease_end_date": add_days(today(), -1),
                "rent_amount": 100,
                "billing_cycle": "Monthly",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop_lease, doc.name)
        apply_workflow(doc, "Submit for Approval")
        apply_workflow(doc, "Approve")
        self.assertEqual(doc.docstatus, 1, "the fixture must be a submitted lease")
        self.assertEqual(doc.status, "Approved")
        return doc

    def test_every_status_the_select_allows_is_a_workflow_state(self):
        """The root of it. A value the Select permits but the Workflow does not know is
        a value the document can hold and the state machine cannot reason about."""
        allowed = {
            o.strip()
            for o in (frappe.get_meta("Lease").get_field("status").options or "").split("\n")
            if o.strip()
        }
        states = set(
            frappe.get_all(
                "Workflow Document State",
                filters={"parent": WORKFLOW},
                pluck="state",
            )
        )
        self.assertEqual(
            sorted(allowed - states),
            [],
            "the Select allows statuses the Lease Workflow has no state for",
        )

    def test_the_workflow_state_field_really_is_status(self):
        """If this ever changes, the test above is measuring the wrong field."""
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )

    def test_the_scheduler_leaves_the_lease_saveable(self):
        """The failing sequence from the card, end to end."""
        from apex.habitat.tasks.residency import lease_expiry_watchlist

        lease = self._expired_lease()
        lease_expiry_watchlist()
        lease.reload()
        self.assertEqual(lease.status, "Expired", "the job did not run on this fixture")
        lease.save(ignore_permissions=True)
        lease.reload()
        self.assertEqual(
            lease.status,
            "Expired",
            "saving the lease moved it off the status the scheduler set",
        )
