# Copyright (c) 2026, afmcoltd
"""Tests for Vehicle Incident's own draft guards and cost-recovery arithmetic.

Patterned on frappe/tests/test_document.py. Most cases build an unsaved
Document via frappe.new_doc and call one guard method directly. The
status-transition refusal is the exception: ``has_value_changed`` only knows
about a change once the document has been loaded from the database, so that
one case inserts a minimal incident against the fixture vehicle and reloads
it before asserting the refusal.

WHY ``test_ignore`` NAMES ``Loan``. ``get_dependencies`` (frappe/test_runner.py:359-381)
builds a test record for every Link on the DocType under test, whether or not a case
touches it. ``recovery_loan`` Links to ``Loan``, which the ``lending`` app owns, and
apex declares only frappe, erpnext and hrms — so on a site without lending the walk
aborts the WHOLE suite with ``DocType Loan not found`` before one case runs, which
reads as UNKNOWN rather than as a failure. ``test_ignore`` (test_runner.py:374-377) is
the framework's own hatch for this and is scoped to this module alone. It is honest
here because nothing below reads ``recovery_loan``; the cases that do live in
``test_vehicle_incident_loan_recovery.py`` and skip themselves when lending is absent.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests._helpers import lending_installed

test_dependencies = ["Salis Vehicle"]
test_ignore = ["Loan"]


class TestVehicleIncident(FrappeTestCase):
    def _incident(self, **fields):
        doc = frappe.new_doc("Vehicle Incident")
        doc.update(
            {
                "incident_type": "Accident",
                "vehicle": "_T ABC 1001",
                "incident_date": today(),
                "description": "Test collision.",
            }
        )
        doc.update(fields)
        return doc

    # -- status stays under controller-owned transitions --

    def test_a_new_incident_is_forced_to_open_regardless_of_caller_input(self):
        doc = self._incident(status="Closed")
        doc._guard_status()
        self.assertEqual(doc.status, "Open")

    def test_changing_status_on_a_saved_incident_outside_the_actions_is_refused(self):
        doc = self._incident()
        doc.insert()
        reloaded = frappe.get_doc("Vehicle Incident", doc.name)
        reloaded.status = "Closed"
        self.assertRaises(frappe.PermissionError, reloaded._guard_status)

    # -- date and cost sanity, exercised through the whole validate() --

    def test_incident_date_in_the_future_is_refused(self):
        doc = self._incident(incident_date=add_days(today(), 1))
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_incident_date_today_is_accepted(self):
        doc = self._incident(incident_date=today())
        doc.validate()

    def test_negative_estimated_cost_is_refused(self):
        doc = self._incident(estimated_cost=-1)
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_zero_estimated_cost_is_accepted(self):
        doc = self._incident(estimated_cost=0)
        doc.validate()

    # -- third-party block follows its own flag --

    def test_third_party_fields_are_cleared_once_the_flag_is_off(self):
        doc = self._incident(
            third_party_involved=0,
            third_party_plate="ABC 123",
            third_party_driver="Someone",
        )
        doc._sync_third_party()
        self.assertIsNone(doc.third_party_plate)
        self.assertIsNone(doc.third_party_driver)

    def test_third_party_fields_survive_while_the_flag_is_on(self):
        doc = self._incident(third_party_involved=1, third_party_plate="ABC 123")
        doc._sync_third_party()
        self.assertEqual(doc.third_party_plate, "ABC 123")

    # -- wage-recovery consent and arithmetic --

    def test_recovery_amount_must_be_positive(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=0)
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_recovery_amount_cannot_exceed_the_estimated_cost(self):
        doc = self._incident(
            recover_from_driver=1, estimated_cost=500, recovery_amount=600
        )
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_recovery_amount_within_the_estimated_cost_is_accepted(self):
        doc = self._incident(
            recover_from_driver=1,
            estimated_cost=500,
            recovery_amount=400,
            worker_signature="sig",
        )
        with lending_installed():
            doc._guard_cost_recovery()

    def test_installment_amount_cannot_exceed_the_recovery_amount(self):
        doc = self._incident(
            recover_from_driver=1,
            estimated_cost=500,
            recovery_amount=400,
            installment_amount=450,
            worker_signature="sig",
        )
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_submitting_a_recovery_without_a_worker_signature_is_refused(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=400)
        doc.docstatus = 1
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_a_worker_signature_stamps_todays_date_once(self):
        doc = self._incident(
            recover_from_driver=1,
            recovery_amount=400,
            worker_signature="sig",
            signed_on=None,
        )
        with lending_installed():
            doc._guard_cost_recovery()
        self.assertEqual(doc.signed_on, today())
