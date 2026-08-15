# Copyright (c) 2026, AFMCO and contributors
"""the two read-only logs must be reachable from somewhere.

`Boarding Scan Log` and `Trip Start Log` both carry `read_only=1`. Frappe reads that flag as
"User Cannot Search" (`frappe/utils/user.py:139-140`), so neither DocType is added to
`can_search` and no desk route reaches either log. Their reports were therefore the only
path to the data — and neither report was linked from any workspace, so the only way in was
to know the URL and type it.

This holds the pair together: while a log stays read-only, its register must stay linked. If
someone later clears `read_only` the desk list becomes reachable and the link is merely
convenient; while it is set, the link is the access path.
"""

import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

WORKSPACE = "Salis"

# log DocType -> the register that is its only path while the log is read-only
GATED = {
    "Boarding Scan Log": "Boarding Scan Register",
    "Trip Start Log": "Trip Start Register",
}


class TestTheReadOnlyLogsAreReachable(FrappeTestCase):
    def _workspace_reports(self):
        path = (
            pathlib.Path(frappe.get_app_path("apex"))
            / "salis"
            / "workspace"
            / "salis"
            / "salis.json"
        )
        links = json.loads(path.read_text())["links"]
        return {row.get("link_to") for row in links if row.get("link_type") == "Report"}

    def test_each_gated_log_is_still_read_only(self):
        """If this ever flips, the rule below stops being load-bearing — but it must be
        noticed rather than silently outgrown."""
        for log in GATED:
            with self.subTest(doctype=log):
                self.assertTrue(
                    frappe.get_meta(log).read_only,
                    f"{log} is no longer read_only; re-check whether its register is "
                    "still the only path",
                )

    def test_a_read_only_doctype_is_excluded_from_search(self):
        """The framework rule this rests on, asserted rather than quoted."""
        from frappe.utils.user import UserPermissions

        user = UserPermissions("Administrator")
        user.build_permissions()
        for log in GATED:
            with self.subTest(doctype=log):
                self.assertNotIn(
                    log,
                    user.can_search,
                    f"{log} is searchable, so the register is not the only path",
                )

    def test_each_register_is_linked_from_the_workspace(self):
        linked = self._workspace_reports()
        for log, report in GATED.items():
            with self.subTest(report=report):
                self.assertIn(
                    report,
                    linked,
                    f"{report} is the only path to {log} and no workspace links it",
                )

    def test_each_register_exists_as_a_standard_report(self):
        for log, report in GATED.items():
            with self.subTest(report=report):
                self.assertTrue(frappe.db.exists("Report", report))
                self.assertEqual(
                    frappe.db.get_value("Report", report, "ref_doctype"), log
                )
