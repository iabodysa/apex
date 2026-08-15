# Copyright (c) 2026, AFMCO and contributors
"""A-411 — the scheduler must not write a status the Workflow cannot validate.

`status` on Lease is the Workflow's state field, and the Lease Workflow knows four
states: Draft, Pending Approval, Approved, Rejected. The Select allows three more —
Active, Expired, Terminated — and `lease_expiry_watchlist` writes Expired straight to
the database. The document then sits in a value its own state machine does not contain.

The failing sequence the card names is the first test here: approve a lease, backdate
its end date, run the job, then open and save it.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

WORKFLOW = "Lease Workflow"


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestTheWorkflowOwnsEveryStatusItIsGiven(FrappeTestCase):
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
