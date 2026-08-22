# Copyright (c) 2026, afmcoltd
"""What a Vehicle Damage Write-Off guarantees, asserted against the DocType itself.

A case cannot move past Open without evidence. ``estimated_cost`` cannot be
negative. Above the Write-Off Operations Threshold (default 2000, read from
Salis Settings), ``needs_operations`` is server-derived and a case that needs
Operations authority can only be approved by a Fleet Manager / System
Manager — a plain Fleet Supervisor is refused even with evidence on file.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]

_SUPERVISOR_ONLY_USER = "vehicle-damage-write-off-doa-test@example.invalid"


def _ensure_supervisor_only_user():
    if not frappe.db.exists("User", _SUPERVISOR_ONLY_USER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SUPERVISOR_ONLY_USER,
                "first_name": "Vehicle Write-Off DoA Test",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Supervisor"}],
            }
        ).insert(ignore_permissions=True)
    return _SUPERVISOR_ONLY_USER


class TestVehicleDamageWriteOff(FrappeTestCase):
    def test_moving_past_open_without_evidence_is_refused(self):
        """A write-off case cannot progress on a bare say-so; it needs recorded evidence."""
        write_off = frappe.copy_doc(frappe.get_test_records("Vehicle Damage Write-Off")[0])
        write_off.evidence = None
        write_off.status = "Under Review"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Evidence is required",
            write_off.insert,
        )

    def test_a_negative_estimated_cost_is_refused(self):
        """A write-off cannot claim a negative cost."""
        write_off = frappe.copy_doc(frappe.get_test_records("Vehicle Damage Write-Off")[0])
        write_off.estimated_cost = -100
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Estimated cost cannot be negative",
            write_off.insert,
        )

    def test_a_high_value_write_off_cannot_be_approved_by_a_fleet_supervisor_alone(self):
        """Past the Operations threshold, only Operations-tier authority may approve.

        Inserts with ``ignore_permissions``: this DocType carries no ``project``
        field, so ``apex.salis.permissions.scoped_has_permission`` denies
        "create" outright to any non-owner, non-unscoped role before a row
        exists to own — a separate project-scoping finding, not the DoA gate
        this test targets. Bypassing it here isolates ``_enforce_doa_gate``,
        which reads ``frappe.get_roles()`` and is unaffected by that bypass.
        """
        approver = _ensure_supervisor_only_user()
        write_off = frappe.copy_doc(frappe.get_test_records("Vehicle Damage Write-Off")[0])
        write_off.estimated_cost = 10000
        write_off.status = "Approved"

        with self.set_user(approver):
            self.assertRaisesRegex(
                frappe.ValidationError,
                "can only be approved by Operations-tier authority",
                lambda: write_off.insert(ignore_permissions=True),
            )
