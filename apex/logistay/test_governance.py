# Copyright (c) 2026, AFMCO and contributors
"""P-193 acceptance tests — shared governance: DoA / SoD / Audit / Export.

All fixtures are SYNTHETIC (fake role names, fake users, round fake amounts, a
PLANTED fake SA-IBAN that is 'SA' + 22 constant digits). No real DoA threshold,
role, approver, or account value appears. Proven against ``logistay_governance.
enforce_gate``:

* DoA BAND ROLE   — an amount inside a band requires the mapped approver role;
  an approver lacking both the required role and the escalation role is BLOCKED
  (authority_unknown).
* SoD            — the preparer may not be the approver (maker != checker), and
  even two DISTINCT users are blocked if they SHARE a controlling role (a
  preparer cannot approve their own doc via a second role).
* UNCONFIGURED   — no band for the action is a fail-closed block (never a default
  approver).
* AUDIT          — every governance decision writes an immutable Audit Event
  (append-only: no edit, no delete).
* EXPORT         — the export boundary is fail-closed: an owner-internal export
  passes, a client-audience export is HELD (the out-of-repo V2 scanner is
  unwired, so any third-audience export is treated as UNSCANNED = blocked). The
  planted synthetic SA-IBAN is recognised by the pure ``valid_sa_iban`` format
  detector; the actual IBAN-regex detection lives in the out-of-repo scanner
  (documented gap).

Isolation: setUp deactivates any pre-seeded active DoA Bands for the action so
exactly ONE synthetic band resolves; FrappeTestCase rolls the change back.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.payroll_gate import valid_sa_iban
from apex.logistay_governance.enforce_gate import enforce_gate, gate_export, write_audit

# A planted, obviously-synthetic SA IBAN: 'SA' + 22 identical digits. NOT a real
# account — used only to prove the format detector and the export hold.
PLANTED_SA_IBAN = "SA" + "4" * 22


def _suffix() -> str:
    return frappe.generate_hash(length=12)


class _GovFixture(FrappeTestCase):
    ACTION = "invoice_issuance"

    def setUp(self):
        frappe.set_user("Administrator")
        # Deactivate any pre-seeded active bands for the action -> deterministic
        # single-band resolution. Rolled back by FrappeTestCase after the test.
        for name in frappe.get_all(
            "DoA Band", filters={"gov_action": self.ACTION, "gov_active": 1}, pluck="name"
        ):
            frappe.db.set_value("DoA Band", name, "gov_active", 0)

    def _role(self) -> str:
        role = frappe.get_doc({"doctype": "Role", "role_name": f"LGZT Approver {_suffix()}"})
        role.insert(ignore_permissions=True)
        return role.name

    def _user(self, *roles) -> str:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"lgzt-{_suffix()}@example.com",
                "first_name": "LGZT",
                "send_welcome_email": 0,
            }
        )
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
        if roles:
            user.add_roles(*roles)
        return user.name

    def _band(self, role, action=None, amount_from=0, amount_to=1_000_000) -> str:
        seq = int(_suffix()[:8], 16) % 1_000_000
        band = frappe.get_doc(
            {
                "doctype": "DoA Band",
                "gov_action": action or self.ACTION,
                "gov_band_seq": seq,
                "gov_active": 1,
                "gov_amount_from": amount_from,
                "gov_amount_to": amount_to,
                "gov_required_role": role,
                "gov_effective_from": "2020-01-01",
            }
        )
        band.insert(ignore_permissions=True)
        return band.name


class TestDoAAndSoD(_GovFixture):
    def test_maker_cannot_be_checker(self):
        role = self._role()
        self._band(role)
        u = self._user(role)
        with self.assertRaises(frappe.ValidationError):
            enforce_gate("Sales Invoice", f"LGZT-INV-{_suffix()}", self.ACTION, 500_000, u, u)

    def test_shared_controlling_role_blocks_two_distinct_users(self):
        # A preparer cannot approve their own doc even via a second role: both
        # hold the band's controlling role -> SoD-ROLE-DISJOINT violation.
        role = self._role()
        self._band(role)
        preparer = self._user(role)
        approver = self._user(role)
        with self.assertRaises(frappe.ValidationError):
            enforce_gate("Sales Invoice", f"LGZT-INV-{_suffix()}", self.ACTION, 500_000, preparer, approver)

    def test_approver_without_mapped_role_is_blocked(self):
        role = self._role()
        self._band(role)
        preparer = self._user()  # no controlling role
        approver = self._user()  # lacks the band's required role
        with self.assertRaises(frappe.ValidationError):
            enforce_gate("Sales Invoice", f"LGZT-INV-{_suffix()}", self.ACTION, 500_000, preparer, approver)

    def test_mapped_approver_is_allowed_and_audited(self):
        role = self._role()
        self._band(role)
        preparer = self._user()
        approver = self._user(role)
        entity_id = f"LGZT-INV-{_suffix()}"
        verdict = enforce_gate("Sales Invoice", entity_id, self.ACTION, 500_000, preparer, approver)
        self.assertEqual(verdict, "ALLOW")
        # Every governance decision writes an Audit Event.
        approvals = frappe.get_all(
            "Audit Event",
            filters={"gov_entity_id": entity_id, "gov_action": "doa_approve"},
        )
        self.assertEqual(len(approvals), 1)

    def test_unconfigured_action_is_fail_closed(self):
        # No band at all for this action -> doa_band_unconfigured block.
        action = "credit_note_issue"
        frappe.db.delete("DoA Band", {"gov_action": action})
        preparer = self._user()
        approver = self._user()
        with self.assertRaises(frappe.ValidationError):
            enforce_gate("Credit Note", f"LGZT-CN-{_suffix()}", action, 500_000, preparer, approver)


class TestAuditAppendOnly(_GovFixture):
    def test_write_audit_creates_an_event(self):
        entity_id = f"LGZT-E-{_suffix()}"
        name = write_audit("Sales Invoice", entity_id, "invoice_issue", "Administrator")
        self.assertTrue(frappe.db.exists("Audit Event", name))

    def test_audit_event_cannot_be_edited(self):
        name = write_audit("Sales Invoice", f"LGZT-E-{_suffix()}", "invoice_issue", "Administrator")
        evt = frappe.get_doc("Audit Event", name)
        evt.gov_subject_key = "tampered"
        with self.assertRaises(frappe.ValidationError):
            evt.save(ignore_permissions=True)

    def test_audit_event_cannot_be_deleted(self):
        name = write_audit("Sales Invoice", f"LGZT-E-{_suffix()}", "invoice_issue", "Administrator")
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("Audit Event", name, ignore_permissions=True)


class TestExportBoundary(_GovFixture):
    def test_planted_synthetic_iban_is_well_formed(self):
        # The pure format detector recognises the planted synthetic SA-IBAN;
        # the actual regex leak-scan is the out-of-repo V2 scanner (gap).
        self.assertTrue(valid_sa_iban(PLANTED_SA_IBAN))

    def test_owner_internal_export_passes(self):
        self.assertEqual(
            gate_export(f"LGZT-FILE-{_suffix()}-{PLANTED_SA_IBAN}", "owner_internal", "Administrator"),
            "pass",
        )

    def test_client_export_is_held_fail_closed(self):
        # A third-audience export carrying the planted synthetic SA-IBAN is HELD
        # (unscanned = fail-closed) and an export_block Audit Event is written.
        file_ref = f"LGZT-FILE-{_suffix()}-{PLANTED_SA_IBAN}"
        with self.assertRaises(frappe.ValidationError):
            gate_export(file_ref, "client", "Administrator")
        blocks = frappe.get_all("Audit Event", filters={"gov_action": "export_block"})
        self.assertTrue(blocks)


if __name__ == "__main__":
    import unittest

    unittest.main()
