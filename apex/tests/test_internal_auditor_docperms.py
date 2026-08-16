# Copyright (c) 2026, AFMCO and contributors
"""The Internal Auditor may read and report on the custody, asset and ledger set, and write none of it.

WHY THIS ASKS THE FRAMEWORK RATHER THAN THE FILE. The previous version opened each DocType's
JSON and asserted the permissions block contained what the permissions block contained — a
Change Detector Test, pinning the file's text rather than the system's behaviour. It could not
fail for any reason a reader would care about: edit the JSON and the test either follows the edit
or is updated to match it. The behaviour an auditor actually meets is decided by
`frappe.has_permission`, which reads DocPerm rows, Custom DocPerm rows, User Permissions and any
`has_permission` hook together — none of which the JSON alone can answer for.

So this asks the live question once per DocType, as the role, and the ten one-assertion methods
become one behaviour with a message per DocType. That is a smaller test proving strictly more.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user

ROLE = "Internal Auditor"
AUDITOR = "internal_auditor_docperms@example.com"

READ_ONLY_DOCTYPES = (
    "Custody Issue",
    "Custody Return",
    "Custody Damage Assessment",
    "Facility Asset",
    "Facility Asset Movement",
    "Facility Asset Custody Assignment",
    "Utility Bill Entry",
    "Lease",
    "Accommodation Ledger",
    "Cleaning Log",
)

FORBIDDEN = ("write", "create", "delete", "submit", "cancel", "amend")


class TestInternalAuditorPermissions(FrappeTestCase):
    """What the Internal Auditor role can and cannot do, asked of the framework."""

    @classmethod
    def setUpClass(cls):
        """Create the auditor once; the role grant is what the whole class exercises."""
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.auditor = _user(AUDITOR, ROLE)

    def test_the_auditor_reads_and_reports_every_doctype_in_the_set(self):
        """Read and report are the two the role exists for."""
        with as_user(self.auditor):
            for doctype in READ_ONLY_DOCTYPES:
                self.assertTrue(
                    frappe.has_permission(doctype, "read"),
                    f"{doctype}: the auditor must be able to read it",
                )
                self.assertTrue(
                    frappe.has_permission(doctype, "report"),
                    f"{doctype}: the auditor must be able to report on it",
                )

    def test_the_auditor_cannot_change_anything_in_the_set(self):
        """A read-only role that can submit or delete is not a read-only role."""
        with as_user(self.auditor):
            for doctype in READ_ONLY_DOCTYPES:
                for action in FORBIDDEN:
                    self.assertFalse(
                        frappe.has_permission(doctype, action),
                        f"{doctype}: the auditor must NOT be able to {action}",
                    )

    def test_the_scan_is_non_vacuous(self):
        """A permission check against a DocType with no table would pass for the wrong reason."""
        for doctype in READ_ONLY_DOCTYPES:
            self.assertTrue(
                frappe.db.table_exists(doctype),
                f"{doctype} is named by this guard but has no table on the site",
            )
