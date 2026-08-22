# Copyright (c) 2026, afmcoltd
"""What a Movement Cost Recovery guarantees, asserted against the DocType itself.

The amount must be positive. Marking a recovery Approved (or Recovered)
requires basis/evidence and an acknowledgement already on file. Above the
Cost Recovery Operations Threshold (default 1000, read from Salis Settings),
``needs_operations`` is server-derived and a recovery that needs Operations
authority can only be approved by a Fleet Manager / System Manager — a plain
Fleet Supervisor is refused even with every other precondition met.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver"]

_SUPERVISOR_ONLY_USER = "movement-cost-recovery-doa-test@example.invalid"


def _ensure_supervisor_only_user():
    if not frappe.db.exists("User", _SUPERVISOR_ONLY_USER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SUPERVISOR_ONLY_USER,
                "first_name": "Movement Cost Recovery DoA Test",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Supervisor"}],
            }
        ).insert(ignore_permissions=True)
    return _SUPERVISOR_ONLY_USER


class TestMovementCostRecovery(FrappeTestCase):
    def test_a_zero_or_negative_amount_is_refused(self):
        """A recovery for nothing (or less) recovers nothing."""
        recovery = frappe.copy_doc(frappe.get_test_records("Movement Cost Recovery")[0])
        recovery.amount = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Amount must be greater than zero",
            recovery.insert,
        )

    def test_marking_approved_without_evidence_is_refused(self):
        """A recovery cannot be approved on a bare say-so; it needs a recorded basis."""
        recovery = frappe.copy_doc(frappe.get_test_records("Movement Cost Recovery")[0])
        recovery.basis_evidence = None
        recovery.status = "Approved"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Basis / Evidence is required",
            recovery.insert,
        )

    def test_a_high_value_recovery_cannot_be_approved_by_a_fleet_supervisor_alone(self):
        """Past the Operations threshold, only Operations-tier authority may approve."""
        approver = _ensure_supervisor_only_user()
        recovery = frappe.copy_doc(frappe.get_test_records("Movement Cost Recovery")[0])
        recovery.amount = 5000
        recovery.acknowledgement_received = 1
        recovery.status = "Approved"

        with self.set_user(approver):
            self.assertRaisesRegex(
                frappe.ValidationError,
                "can only be approved by Operations-tier authority",
                recovery.insert,
            )
