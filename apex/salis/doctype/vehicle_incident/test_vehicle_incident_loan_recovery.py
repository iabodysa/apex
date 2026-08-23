# Copyright (c) 2026, afmcoltd
"""Vehicle Incident's own half of the Loan hand-off: the link it stores, and the
refusal/reversal pair a cancel must run for whichever recovery record it holds.

The Loan itself (its schedule, its cap, hrms's own deduction) is proved in
apex.apex_core.utils.test_employee_loan_recovery against a real Salary Slip; this
module never builds one, only the incident's own bookkeeping around it.

``test_ignore`` names ``Loan`` for the same reason ``test_vehicle_incident.py`` does:
``get_dependencies`` (frappe/test_runner.py:359-381) walks ``recovery_loan``'s Link and
would abort the whole suite on a site without the ``lending`` app, which apex does not
declare. Nothing here inserts a real Loan — ``raise_recovery_loan`` is patched — so the
hatch (test_runner.py:374-377) costs this module no coverage.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import as_user

test_dependencies = ["Salis Vehicle"]
test_ignore = ["Loan"]

_MODULE = "apex.salis.doctype.vehicle_incident.vehicle_incident"


class TestVehicleIncidentRaisesALoanNotAnAdvance(FrappeTestCase):
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

    def test_raising_never_raises_a_legacy_employee_advance(self):
        """The regression this guards: a stray import of the retired call would
        raise BOTH records for one incident."""
        doc = self._incident(recover_from_driver=1, recovery_amount=400)
        doc.insert()
        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-NEW"):
            doc._raise_recovery_loan()
        self.assertFalse(doc.recovery_advance)


class TestVehicleIncidentCancelGuardsTheLoan(FrappeTestCase):
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
        """The order this guards: Loan.on_cancel refuses while a submitted Loan
        Disbursement still links it (lending/loan_management/doctype/loan/loan.py:118
        only ignores GL Entry / Payment Ledger Entry), so the disbursement must go
        first."""
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

        # The negative control: nothing in THIS module refuses a second raise once
        # the link is blank. Calling the internal method directly (bypassing
        # submit(), which is exactly what Frappe's own docstatus rule prevents)
        # shows the risk is real — the safeguard here is Frappe's transition rule,
        # not an extra check of our own.
        with patch(f"{_MODULE}.raise_recovery_loan", return_value="LOAN-SECOND") as mock_direct:
            reloaded._raise_recovery_loan()
        mock_direct.assert_called_once()
