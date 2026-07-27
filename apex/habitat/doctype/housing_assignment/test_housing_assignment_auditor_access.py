# Copyright (c) 2026, AFMCO and contributors
"""A-216 — Internal Auditor reads Housing Assignment, and cannot export it.

THE CONTRADICTION THIS CLOSES
-----------------------------
`Internal Auditor` was already named in `habitat/permissions.py` HOUSING_UNSCOPED_ROLES,
the set that lifts the building filter — so the exemption had been written for a role that
held NO DocPerm row on Housing Assignment at all, and therefore could not read one row in
any building. Meanwhile three shipped reports name the role in their `roles` table, so
`boot.get_user_pages_or_reports` put them in its Reports list and
`frappe/desk/query_report.py:47` threw on every click.

The owner's decision: grant `read` and `report` at permlevel 0, WITHHOLD `export`.

`export` is withheld by OMITTING the key from the row, never by writing 0. `import_file`
skips field defaults (`document.py:833` under `frappe.flags.in_import`), so an omitted flag
lands as 0 anyway, while an explicit `"export": 0` reads to the next editor as a toggle
someone meant to flip.

THE LIMIT, STATED PLAINLY — see the long note in
`apex_core/utils/test_report_role_guard.py`. Withholding `export` gates the DOWNLOAD
endpoint (`query_report.py:323` -> `permissions.py:608-616`); it hides no row. All three
reports read with `frappe.get_all`, which sets `ignore_permissions`
(`frappe/__init__.py:2050`), so the DocPerm is not what confines their rows — each report's
own Python is. For this role that changes nothing, because it is unscoped by design.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.housing_assignment.test_housing_assignment_auditor_access
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.desk.query_report import get_report_doc
from frappe.tests.utils import FrappeTestCase

_HOUSING_ASSIGNMENT_JSON = Path(__file__).resolve().parent / "housing_assignment.json"

AUDITOR_ROLE = "Internal Auditor"
THE_THREE_REPORTS = (
    "Accommodation Occupancy Summary",
    "Active Resident Register",
    "Idle Resident Detection",
)


class TestInternalAuditorHousingAccess(FrappeTestCase):
    """Site-bound. `frappe.session.user` is process state that no rollback restores, so the
    cleanup is registered BEFORE anything sets it."""

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _auditor(self):
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a216_{frappe.generate_hash(length=12)}@example.com",
                "first_name": "Auditor",
                "roles": [{"role": AUDITOR_ROLE}],
            }
        ).insert(ignore_permissions=True).name

    # ------------------------------------------------------------------ the pair, one method

    def test_the_auditor_opens_the_report_and_is_refused_the_export(self):
        """THE PAIR. Both halves in one method, asserted explicitly different at the end —
        a bug that granted everything would satisfy the open, and a bug that granted
        nothing would satisfy the refusal. Only the contrast proves the shape."""
        auditor = self._auditor()
        frappe.set_user(auditor)

        # Half 1 — THE OPEN. get_report_doc carries both gates the role used to die on:
        # Report.is_permitted() at query_report.py:41 and has_permission(ref, "report")
        # at :47. Calling it is the real open path, not a re-implementation of it.
        opened = get_report_doc("Active Resident Register")
        self.assertEqual(opened.ref_doctype, "Housing Assignment")
        open_verdict = "opened"

        # Half 2 — THE REFUSAL. Caught by NAME: frappe.PermissionError does not descend
        # from ValidationError, so an unrelated validation failure cannot satisfy this.
        with self.assertRaises(frappe.PermissionError) as caught:
            frappe.permissions.can_export("Housing Assignment", raise_exception=True)
        self.assertIn(
            "Housing Assignment",
            str(caught.exception),
            "the export refusal does not name the DocType it refused",
        )
        export_verdict = "refused"

        self.assertNotEqual(
            open_verdict,
            export_verdict,
            "the two halves collapsed into one verdict — the grant is all-or-nothing",
        )
        # And the underlying rights, so the verdicts above cannot both be accidents.
        self.assertIs(frappe.has_permission("Housing Assignment", "read", user=auditor), True)
        self.assertIs(frappe.has_permission("Housing Assignment", "report", user=auditor), True)
        self.assertFalse(
            frappe.permissions.can_export("Housing Assignment"),
            "export leaked back in",
        )

    def test_all_three_formerly_broken_reports_now_open(self):
        """The baseline in test_report_role_guard drained all three together, because they
        turned on one row. If only one of them opens, that drain was wrong."""
        frappe.set_user(self._auditor())
        for report in THE_THREE_REPORTS:
            with self.subTest(report=report):
                doc = get_report_doc(report)
                self.assertEqual(doc.ref_doctype, "Housing Assignment")

    def test_a_role_without_the_row_still_cannot_open_them(self):
        """The control. Without it, a test that passed because the reports stopped checking
        anything would look identical to one that passed because the grant works."""
        outsider = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a216x_{frappe.generate_hash(length=12)}@example.com",
                "first_name": "Outsider",
                "roles": [{"role": "Fleet Supervisor"}],
            }
        ).insert(ignore_permissions=True).name
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            get_report_doc("Active Resident Register")

    # ------------------------------------------------------------------- the shipped row

    def test_the_row_grants_exactly_read_and_report(self):
        """Read off the shipped JSON: a right must be absent by OMISSION, not shipped as 0."""
        shipped = json.loads(_HOUSING_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        rows = [
            p
            for p in shipped["permissions"]
            if p.get("role") == AUDITOR_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(rows), 1, f"expected exactly one permlevel-0 {AUDITOR_ROLE} row")
        row = rows[0]
        self.assertEqual(row.get("read"), 1)
        self.assertEqual(row.get("report"), 1)
        for withheld in (
            "export",
            "write",
            "create",
            "delete",
            "submit",
            "cancel",
            "amend",
            "share",
            "print",
            "email",
        ):
            self.assertNotIn(
                withheld,
                row,
                f"{withheld} must be OMITTED from the row, not shipped as 0 — an explicit "
                "0 reads as a toggle someone meant to flip",
            )

    def test_the_grant_did_not_disturb_the_other_roles(self):
        """A second plain read row for an existing role would silently disable an if_owner
        constraint (permissions.py:286-287). Nothing else on this table may have moved."""
        shipped = json.loads(_HOUSING_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        by_role = {}
        for p in shipped["permissions"]:
            by_role.setdefault(p["role"], []).append(p)
        self.assertEqual(
            sorted(by_role),
            ["Accommodation Manager", AUDITOR_ROLE, "Resident Supervisor", "System Manager"],
            "the role set on Housing Assignment changed beyond the A-216 grant",
        )
        for role, rows in by_role.items():
            self.assertEqual(len(rows), 1, f"{role} gained a second row — check if_owner")

    def test_the_auditor_holds_no_write_authority(self):
        """The read-only shape, proven at runtime rather than inferred from the JSON."""
        auditor = self._auditor()
        for right in ("write", "create", "delete", "submit", "cancel"):
            with self.subTest(right=right):
                self.assertIs(
                    frappe.has_permission("Housing Assignment", right, user=auditor),
                    False,
                    f"the auditor grant leaked {right}",
                )

    def test_the_unscoped_exemption_now_has_a_row_to_apply_to(self):
        """The contradiction, asserted directly: the role is in HOUSING_UNSCOPED_ROLES, and
        it can now actually read the DocType that set was lifting a filter on."""
        from apex.habitat import permissions

        self.assertIn(AUDITOR_ROLE, permissions.HOUSING_UNSCOPED_ROLES)
        auditor = self._auditor()
        self.assertEqual(
            permissions.accommodation_assignment_query(auditor),
            "",
            "an unscoped role must get an empty row filter",
        )
        self.assertIs(frappe.has_permission("Housing Assignment", "read", user=auditor), True)
