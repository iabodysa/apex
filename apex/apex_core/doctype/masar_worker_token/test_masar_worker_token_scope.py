# Copyright (c) 2026, afmcoltd
"""Row-scoping for Masar Worker Token's desk read surfaces (list/report/print).

``masar_worker_token_scope_query`` / ``masar_worker_token_has_permission``
(``apex.apex_core.utils.portal_identity``) are the read-side counterpart to
``authorize_issuance``'s write-side scope check: same ``ISSUER_ROLES`` /
``_UNSCOPED_ISSUER_ROLES`` tables, same Project/Building axis per ``holder_type``. A
plain ``TestCase`` on purpose, mocking ``frappe.get_roles``/``frappe.db.get_value``/
``frappe.get_all`` and the lazily-imported ``apex.salis.permissions`` /
``apex.habitat.permissions`` resolvers, because the underlying Project/Building
primitives (``_allowed_projects``, ``_allowed_buildings``,
``permission_scope.scope_condition``) already have their own security-oracle suite in
``apex.apex_core.utils.test_permission_scope_shared``; what is under test HERE is the
holder_type dispatch and the audience tables, not the primitives it calls.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.apex_core.utils import portal_identity as security


def _driver_clause(projects):
    escaped = ", ".join(frappe.db.escape(v) for v in projects)
    return (
        "(`holder_type` = 'Driver' and `driver` in ("
        "select `name` from `tabSalis Driver` where `project` in ({0})))"
    ).format(escaped)


def _worker_clause(buildings):
    escaped = ", ".join(frappe.db.escape(v) for v in buildings)
    return (
        "(`holder_type` = 'Worker' and `employee` in ("
        "select `employee` from `tabHousing Assignment` where `docstatus` = 1 "
        "and `check_out_date` is null and `building` in ({0})))"
    ).format(escaped)


class TestMasarWorkerTokenScopeQuery(TestCase):
    def test_administrator_is_unrestricted(self):
        self.assertEqual(security.masar_worker_token_scope_query(user="Administrator"), "")

    def test_a_role_holding_neither_issuer_set_sees_nothing(self):
        with patch.object(security.frappe, "get_roles", return_value={"Employee"}):
            self.assertEqual(
                security.masar_worker_token_scope_query(user="nobody@example.com"), "1=0"
            )

    def test_fleet_manager_sees_every_driver_row_and_no_worker_row(self):
        with patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}):
            query = security.masar_worker_token_scope_query(user="fm@example.com")
        self.assertEqual(query, "(`holder_type` = 'Driver')")

    def test_hr_user_sees_every_worker_row_and_no_driver_row(self):
        with patch.object(security.frappe, "get_roles", return_value={"HR User"}):
            query = security.masar_worker_token_scope_query(user="hr@example.com")
        self.assertEqual(query, "(`holder_type` = 'Worker')")

    def test_a_role_in_both_issuer_sets_unions_both_unrestricted_clauses(self):
        with patch.object(security.frappe, "get_roles", return_value={"System Manager"}):
            query = security.masar_worker_token_scope_query(user="sm@example.com")
        self.assertEqual(query, "(`holder_type` = 'Driver' or `holder_type` = 'Worker')")

    def test_fleet_supervisor_is_confined_to_their_projects(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch(
                "apex.salis.permissions._allowed_projects",
                return_value=["PROJ-A", "PROJ-B"],
            ),
        ):
            query = security.masar_worker_token_scope_query(user="fs@example.com")
        self.assertEqual(query, "({0})".format(_driver_clause(["PROJ-A", "PROJ-B"])))

    def test_fleet_supervisor_with_no_project_sees_nothing(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch("apex.salis.permissions._allowed_projects", return_value=[]),
        ):
            query = security.masar_worker_token_scope_query(user="fs@example.com")
        self.assertEqual(query, "(1=0)")

    def test_resident_supervisor_is_confined_to_their_buildings(self):
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch("apex.habitat.permissions._allowed_buildings", return_value=["BLD-A"]),
        ):
            query = security.masar_worker_token_scope_query(user="rs@example.com")
        self.assertEqual(query, "({0})".format(_worker_clause(["BLD-A"])))


class TestMasarWorkerTokenHasPermission(TestCase):
    def _doc(self, **fields):
        return frappe._dict(fields)

    def test_a_write_ptype_always_defers_regardless_of_role(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with patch.object(security.frappe, "get_roles", return_value=set()):
            for ptype in ("write", "create", "delete", "submit"):
                with self.subTest(ptype=ptype):
                    self.assertIsNone(
                        security.masar_worker_token_has_permission(
                            doc, ptype, user="anyone@example.com"
                        )
                    )

    def test_administrator_may_read_everything(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        self.assertIsNone(
            security.masar_worker_token_has_permission(doc, "read", user="Administrator")
        )

    def test_a_role_outside_the_docs_audience_issuer_set_is_denied(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="fm@example.com")
            )

    def test_an_unscoped_role_reads_a_row_without_resolving_its_project(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Manager"}),
            patch.object(security.frappe.db, "get_value") as get_value,
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "read", user="fm@example.com")
            )
        get_value.assert_not_called()

    def test_a_scoped_fleet_supervisor_is_admitted_when_the_drivers_project_is_allowed(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch.object(security.frappe.db, "get_value", return_value="PROJ-A"),
            patch(
                "apex.salis.permissions._allowed_projects",
                return_value=["PROJ-A", "PROJ-B"],
            ),
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "report", user="fs@example.com")
            )

    def test_a_scoped_fleet_supervisor_is_denied_when_the_drivers_project_is_not_allowed(self):
        doc = self._doc(holder_type="Driver", driver="DRV-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Fleet Supervisor"}),
            patch.object(security.frappe.db, "get_value", return_value="PROJ-A"),
            patch("apex.salis.permissions._allowed_projects", return_value=["PROJ-B"]),
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "print", user="fs@example.com")
            )

    def test_a_resident_supervisor_is_admitted_when_every_live_building_is_allowed(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all", return_value=["BLD-A"]),
            patch(
                "apex.habitat.permissions._allowed_buildings",
                return_value=["BLD-A", "BLD-B"],
            ),
        ):
            self.assertIsNone(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )

    def test_a_resident_supervisor_is_denied_when_a_live_building_is_not_allowed(self):
        doc = self._doc(holder_type="Worker", employee="EMP-1")
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all", return_value=["BLD-A", "BLD-C"]),
            patch("apex.habitat.permissions._allowed_buildings", return_value=["BLD-A"]),
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )

    def test_a_worker_doc_with_no_employee_link_is_denied_without_a_lookup(self):
        doc = self._doc(holder_type="Worker", employee=None)
        with (
            patch.object(security.frappe, "get_roles", return_value={"Resident Supervisor"}),
            patch.object(security.frappe, "get_all") as get_all,
        ):
            self.assertFalse(
                security.masar_worker_token_has_permission(doc, "read", user="rs@example.com")
            )
        get_all.assert_not_called()
