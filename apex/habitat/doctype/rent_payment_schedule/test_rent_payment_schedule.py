# Copyright (c) 2026, AFMCO and contributors
"""Rent Payment Schedule: the lease's rent grid, and the rent-reminder scaffolding.

Three pieces ship: this child table, the ``Habitat - Rent Payment Due`` Notification,
and the Lease ``supplier`` field whose description names it as the payee for rent due
reminders. The Notification is Days Before on ``due_date`` with condition
``doc.status == 'Unpaid'``, addressed to the Accommodation Manager and the Finance
Manager, and it warns a week ahead.

Rent is paid externally with no GL leg, so the app never learns that a payment cleared
— a person marks the row Paid. That is what the reminder is FOR: it reaches the two
managers while there is still a week to pay and to record it. It cannot nag, because
``get_documents_for_today`` (frappe/email/doctype/notification/notification.py:157-167)
selects only rows whose ``due_date`` falls on the single day ``today + days_in_advance``,
so each row is mailed once and a row left unpaid is never mailed again.

The table is NOT dead code: ``lease.js`` reads ``payment_schedule`` to pick the
outstanding row behind the Generate Payment button. There is no server-side writer,
which is why the controller is a bare ``Document``.

The two tests below pin the parts that make the alert safe rather than noisy: a notice
period greater than zero, and an amount formatted rather than prefixed with a fixed
currency code.
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

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

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Rent Payment Schedule")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("due_date", field_names)
        self.assertIn("amount", field_names)
        self.assertIn("status", field_names)
        self.assertTrue(len(field_names) > 0)

    def test_the_rent_reminder_warns_once_and_ahead_of_the_due_date(self):
        """Read the shipped JSON, not the DB: a site may legitimately switch this off,
        and asserting the installed record would fail on exactly those sites.

        ``days_in_advance`` is the whole safety of this alert. ``get_documents_for_today``
        (frappe/email/doctype/notification/notification.py:157-167) computes ONE reference
        date, ``today + days_in_advance``, and selects rows whose ``due_date`` falls inside
        that single day — so each row is mailed once, on one day, and a row left unpaid is
        never mailed again. Set this back to 0 and the warning arrives on the due date
        itself, which tells the manager a payment is due the day it is due.
        """
        path = os.path.join(
            frappe.get_app_path("apex"),
            "habitat", "notification", "habitat___rent_payment_due",
            "habitat___rent_payment_due.json",
        )
        with open(path, encoding="utf-8") as handle:
            shipped = json.load(handle)
        self.assertEqual(shipped["document_type"], "Rent Payment Schedule")
        self.assertEqual(shipped["event"], "Days Before")
        self.assertEqual(shipped["condition"], "doc.status == 'Unpaid'")
        self.assertGreater(
            shipped["days_in_advance"],
            0,
            "Habitat - Rent Payment Due warns on the due date itself, leaving no time to "
            "act. Every other dated alert in this app warns ahead.",
        )

    def test_the_rent_reminder_names_no_currency_of_its_own(self):
        """The amount is formatted, never prefixed with a fixed currency code.

        A hardcoded code is wrong on any site whose company does not use it, and the
        subject and message of a Notification are the two places it hides from a form.
        """
        path = os.path.join(
            frappe.get_app_path("apex"),
            "habitat", "notification", "habitat___rent_payment_due",
            "habitat___rent_payment_due.json",
        )
        with open(path, encoding="utf-8") as handle:
            shipped = json.load(handle)
        for field in ("subject", "message"):
            with self.subTest(field=field):
                self.assertIn("frappe.format_value", shipped[field])
                self.assertNotIn("SAR", shipped[field])
