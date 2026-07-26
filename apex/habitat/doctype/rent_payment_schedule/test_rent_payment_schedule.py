# Copyright (c) 2026, AFMCO and contributors
"""Rent Payment Schedule: the lease's rent grid, and the rent-reminder scaffolding.

The reminder is DELIBERATELY INERT and is not a gap to close (A-184). Three pieces
of it ship: this child table, the ``Habitat - Rent Payment Due`` Notification, and
the Lease ``supplier`` field whose description names it as the payee for rent due
reminders. The Notification is complete — Days Before on ``due_date``, condition
``doc.status == 'Unpaid'``, addressed to the Accommodation Manager and the Finance
Manager — but ships ``enabled: 0``, so nothing sends until a site turns it on.

That is the intended shape. Rent is paid externally with no GL leg, so the app
cannot know a payment cleared; only a human flipping the row's Status to Paid stops
the reminder. Enabling it by default would mail two managers every unpaid row on
every lease, daily. Shipping it off makes turning it on a site decision, and
docs/training/costs.md documents the row as tracked by hand.

The table is NOT dead code: ``lease.js`` reads ``payment_schedule`` to pick the
outstanding row behind the Generate Payment button. There is no server-side writer,
which is why the controller is a bare ``Document``.

``test_the_rent_reminder_ships_disabled`` pins the decision, so enabling the
Notification has to be a deliberate edit to a failing assertion rather than a quiet
default flip.
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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


class TestRentPaymentSchedule(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Rent Payment Schedule")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Rent Payment Schedule")
        row.due_date = "2026-07-01"
        row.amount = 5000
        row.status = "Unpaid"
        self.assertEqual(row.doctype, "Rent Payment Schedule")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Rent Payment Schedule")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("due_date", field_names)
        self.assertIn("amount", field_names)
        self.assertIn("status", field_names)
        self.assertTrue(len(field_names) > 0)

    def test_the_rent_reminder_ships_disabled(self):
        """The scaffolding is inert by decision; read the shipped JSON, not the DB.

        A site may legitimately enable the Notification, so asserting the installed
        record would fail on exactly the sites that adopted it.
        """
        path = os.path.join(
            frappe.get_app_path("apex"),
            "habitat", "notification", "habitat___rent_payment_due",
            "habitat___rent_payment_due.json",
        )
        with open(path, encoding="utf-8") as handle:
            shipped = json.load(handle)
        self.assertEqual(shipped["document_type"], "Rent Payment Schedule")
        self.assertEqual(
            shipped["enabled"],
            0,
            "Habitat - Rent Payment Due ships enabled. Rent clears outside the app, so "
            "nothing marks a row Paid automatically and every unpaid row would mail the "
            "Accommodation and Finance Managers daily. Build the paid-detection side "
            "before flipping this, and update the module docstring above.",
        )
