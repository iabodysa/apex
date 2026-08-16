# Copyright (c) 2026, AFMCO and contributors
"""The workflow-state field of every approval / lifecycle
DocType is ``read_only``, so the state is driven only by its native Workflow (or
the server engine) and can never be hand-edited on the form. Utility Bill Entry is
additionally pinned down to the four states its approval workflow actually uses
(the dead Received / Under Review / Paid / Disputed options were dropped).

Asserted against ``frappe.get_meta`` (the migrated DocType), not the on-disk
JSON, so it proves the field reached the database read_only.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

# DocType -> workflow-state field. Each is Workflow- or engine-driven, so its
# state field must be read_only.
STATE_FIELDS = {
    "Utility Bill Entry": "status",
    "Lease": "status",
    "Subcontractor Service Contract": "status",
    "Custody Damage Assessment": "status",
    "Dispatch Trip": "status",
    "Fuel Claim": "status",
    "Movement Cost Recovery": "status",
    "Movement Cost Transfer": "status",
    "Fuel Exception Case": "status",
    "Vehicle Damage Write-Off": "status",
    "Fuel Request": "status",
}


class TestWorkflowStateGovernance(FrappeTestCase):
    def test_state_fields_are_read_only(self):
        offenders = []
        checked = 0
        for doctype, fieldname in STATE_FIELDS.items():
            if not frappe.db.exists("DocType", doctype):
                continue
            checked += 1
            df = frappe.get_meta(doctype).get_field(fieldname)
            self.assertIsNotNone(df, f"{doctype}.{fieldname} field is missing")
            if not df.read_only:
                offenders.append(f"{doctype}.{fieldname}")
        self.assertEqual(
            offenders,
            [],
            "workflow-state fields must be read_only, or a user can type a state the "
            "workflow never granted: " + ", ".join(offenders),
        )
        # guard against the enumeration silently going empty (vacuous pass)
        self.assertGreaterEqual(checked, 10, "expected >=10 state fields, enumeration looks empty")

    def test_utility_bill_entry_status_options_trimmed(self):
        df = frappe.get_meta("Utility Bill Entry").get_field("status")
        options = [o for o in (df.options or "").split("\n") if o]
        self.assertEqual(
            options,
            ["Draft", "Pending Approval", "Approved", "Rejected"],
            "Utility Bill Entry.status must expose only the four approval states "
            "(the dead Received/Under Review/Paid/Disputed options were dropped)",
        )
