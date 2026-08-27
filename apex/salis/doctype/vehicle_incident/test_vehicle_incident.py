# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.model.workflow import WorkflowPermissionError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.doctype.vehicle_incident.vehicle_incident import close_incident
from apex.tests._helpers import as_user, lending_installed

test_dependencies = ["Salis Vehicle"]
test_dependencies = ["Salis Vehicle"]
test_ignore = ["Loan"]

_MODULE = "apex.salis.doctype.vehicle_incident.vehicle_incident"


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

    def _delete_incident(self, name):
        doc = frappe.get_doc("Vehicle Incident", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Vehicle Incident", name, force=True)


    def test_a_new_incident_defaults_to_open_with_no_python_default(self):
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        self.assertEqual(doc.status, "Open")

    def test_a_hand_edited_status_is_refused(self):
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        doc.status = "Closed"
        with self.assertRaises(WorkflowPermissionError):
            doc.save()

    def test_close_travels_through_apply_workflow(self):
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        doc.submit()
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", doc.name, "status"), "Under Review"
        )

        close_incident(doc.name, "Repaired and returned to service.")
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", doc.name, "status"), "Closed"
        )


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


class TestVehicleIncidentRaisesALoanNotAnAdvance(FrappeTestCase):
    def setUp(self):
        self.enterContext(lending_installed())

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

    def test_guest_intake_resets_the_loan_link_too(self):
        doc = self._incident(recover_from_driver=1, recovery_loan="LOAN-SHOULD-NOT-SURVIVE")
        with as_user("Guest"):
            doc._guard_public_intake()
        self.assertFalse(doc.recovery_loan)

    def test_raising_is_skipped_when_recovery_is_not_flagged(self):
        doc = self._incident(recover_from_driver=0)
        doc.insert()
        with patch(f"{_MODULE}.raise_recovery_loan") as mock_raise:
            doc._raise_recovery_loan()
        mock_raise.assert_not_called()
        self.assertFalse(doc.recovery_loan)

    def test_raising_is_skipped_once_a_loan_is_already_linked(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=400)
        doc.insert()
        doc.db_set("recovery_loan", "LOAN-EXISTING")
        with patch(f"{_MODULE}.raise_recovery_loan") as mock_raise:
            doc._raise_recovery_loan()
        mock_raise.assert_not_called()

    def test_raising_stores_the_loan_link_when_one_comes_back(self):
        doc = self._incident(
            recover_from_driver=1, recovery_amount=400, installment_amount=100
        )
        doc.insert()
        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-NEW") as mock_raise:
            doc._raise_recovery_loan()
        mock_raise.assert_called_once()
        self.assertEqual(mock_raise.call_args.kwargs["agreed_installment"], 100)
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", doc.name, "recovery_loan"), "LOAN-NEW"
        )

    def test_flagging_recovery_is_refused_when_the_lending_app_is_absent(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=400, installment_amount=100)
        with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "hrms", "apex"]):
            with self.assertRaises(frappe.ValidationError):
                doc.insert()

    def test_an_unflagged_incident_saves_on_a_site_without_the_lending_app(self):
        doc = self._incident(recover_from_driver=0)
        with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "hrms", "apex"]):
            doc.insert()
        self.assertTrue(frappe.db.exists("Vehicle Incident", doc.name))

    def test_raising_never_raises_a_legacy_employee_advance(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=400)
        doc.insert()
        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-NEW"):
            doc._raise_recovery_loan()
        self.assertFalse(doc.recovery_advance)


class TestVehicleIncidentCancelGuardsTheLoan(FrappeTestCase):
    def setUp(self):
        self.enterContext(lending_installed())

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
        doc.insert()
        return doc

    def test_before_cancel_refuses_once_the_loan_has_a_recovered_principal(self):
        doc = self._incident()
        loan_state = frappe._dict(name="LOAN-1", docstatus=1, total_principal_paid=500)
        with patch.object(doc, "_live_recovery_loan", return_value=loan_state):
            with patch.object(doc, "_live_recovery_advance", return_value=None):
                self.assertRaises(frappe.ValidationError, doc.before_cancel)

    def test_before_cancel_allows_a_loan_that_has_recovered_nothing_yet(self):
        doc = self._incident()
        loan_state = frappe._dict(name="LOAN-1", docstatus=1, total_principal_paid=0)
        with patch.object(doc, "_live_recovery_loan", return_value=loan_state):
            with patch.object(doc, "_live_recovery_advance", return_value=None):
                doc.before_cancel()

    def test_release_cancels_the_disbursement_before_the_loan(self):
        doc = self._incident()
        loan_state = frappe._dict(name="LOAN-1", docstatus=1, total_principal_paid=0)
        cancelled_docs = []
        fake_doc = frappe._dict(cancel=lambda: cancelled_docs.append(fake_doc.doctype))

        def _fake_get_doc(doctype, _name):
            fake_doc.doctype = doctype
            return fake_doc

        with patch.object(doc, "_live_recovery_loan", return_value=loan_state):
            with patch(f"{_MODULE}.frappe.get_all", return_value=["DISB-1"]):
                with patch(f"{_MODULE}.frappe.get_doc", side_effect=_fake_get_doc):
                    doc._release_recovery_loan()

        self.assertEqual(cancelled_docs, ["Loan Disbursement", "Loan"])


class TestClearingTheLinkByHandCannotDoubleRaise(FrappeTestCase):
    def setUp(self):
        self.enterContext(lending_installed())

    """Answers a question raised on review: the ``recovery_loan`` link is
    ``no_copy``/read-only in the UI, but that is hygiene, not the guarantee. The
    real guarantee is Frappe's own docstatus-transition rule
    (frappe/model/document.py:902-908): once a document's ``docstatus`` is already
    1, calling ``submit()`` again routes to the "update_after_submit" action, never
    back through ``on_submit`` — so ``_raise_recovery_loan`` cannot run a second
    time for the same document, whether or not ``recovery_loan`` was cleared by
    hand in between. A second Loan can only ever come from a cancel + amend, which
    is a NEW document with its own, single ``on_submit``.
    """

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

    def test_resubmitting_after_clearing_the_link_does_not_call_raise_again(self):
        doc = self._incident(
            recover_from_driver=1, recovery_amount=400, worker_signature="sig"
        )
        doc.insert()
        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-FIRST") as mock_raise:
            doc.submit()
        mock_raise.assert_called_once()
        self.assertEqual(doc.recovery_loan, "LOAN-FIRST")

        frappe.db.set_value("Vehicle Incident", doc.name, "recovery_loan", None)
        reloaded = frappe.get_doc("Vehicle Incident", doc.name)
        self.assertEqual(reloaded.docstatus, 1)

        with patch(f"{_MODULE}.raise_recovery_loan") as mock_raise_again:
            reloaded.submit()

        mock_raise_again.assert_not_called()

        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-SECOND") as mock_direct:
            reloaded._raise_recovery_loan()
        mock_direct.assert_called_once()
