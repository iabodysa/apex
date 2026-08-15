# Copyright (c) 2026, AFMCO and contributors
"""the create-path ordering hazard in the Salis driver-chain rule.

``Document.insert`` runs ``check_permission("create")`` (frappe/model/document.py:300)
BEFORE ``_validate_links()`` (:302) applies ``fetch_from``. On Vehicle Incident, Vehicle
Damage Write-Off and Vehicle Suspension the driver link the rule scopes on is fetched
from ``vehicle.current_driver``, so at the create check it is EMPTY and the chain resolved
no project. Nothing else could rescue the row — ownership is not an access basis on an
unsaved row, and the driver-own basis needs exactly the link that is still empty —
so the create was denied outright, and a project-scoped Fleet Supervisor could not raise an
incident on their own project's vehicle. The mandatory, never-fetched ``vehicle`` link IS
set at that moment and carries the project directly.

Every test proves the fix BOTH ways: the driver link empty and the vehicle IN project must
defer, the same shape on an out-of-project vehicle must still be refused, and a driver that
DOES resolve keeps deciding the verdict so the fallback can never launder an out-of-scope
driver into an in-scope one.

THE ENTRY POINT IS ONE FUNCTION. ``hooks.py`` registers
``project_scoped_has_permission`` for every scoped Salis DocType; it reads ``doc.doctype``,
looks the DocType up in ``SALIS_SCOPE`` and calls that DocType's rule. All three DocTypes
below take the ``driver_chain`` rule, each with its own driver field.

WHY THESE TESTS ARE SITELESS. The bench is shared, so nothing here touches a site: the two
module-level scope resolvers and the driver resolver are stubbed (the documented stub
points) and ``frappe.db.get_value`` is a constructed lookup over the tables below.

A RUNTIME DEMONSTRATION IS THEREFORE STILL OWED: log in as a Fleet Supervisor holding a
User Permission for one project, create a Vehicle Incident server-side against a vehicle in
that project with ``driver`` unset, and confirm it saves while the same shape on another
project's vehicle raises PermissionError.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from apex.salis import permissions as SP

PROJ_A = "PROJ-A"
PROJ_B = "PROJ-B"

DRIVERS = {"DRV-A": PROJ_A, "DRV-B": PROJ_B, "DRV-NONE": None}
VEHICLES = {"VEH-A": PROJ_A, "VEH-B": PROJ_B, "VEH-NONE": None}

# The three DocTypes whose driver link is fetch_from vehicle.current_driver, each with the
# field name it scopes on — Vehicle Suspension reaches its driver as `related_driver`.
FETCHED_DRIVER_DOCTYPES = [
    ("Vehicle Incident", "driver"),
    ("Vehicle Damage Write-Off", "driver"),
    ("Vehicle Suspension", "related_driver"),
]

_ABSENT = object()


class _ScopeCase(unittest.TestCase):
    """A constructed session, db and scope, and no site anywhere."""

    def setUp(self):
        self._stub_local("session", frappe._dict(user="supervisor@example.com"))
        self._stub_local("db", SimpleNamespace(get_value=self._get_value))
        self.own_driver(None)

    @staticmethod
    def verdict(doc, ptype, user=None):
        """The framework's own entry point, so the dispatch is under test too."""
        return SP.project_scoped_has_permission(doc, ptype, user=user)

    def _stub_local(self, name, value):
        """Install a stub on ``frappe.local``, queueing its restore BEFORE the write.

        `frappe.db` / `frappe.session` are proxies onto `frappe.local`, so a stub left
        installed is inherited by every later test in the run; registering the cleanup
        after the mutation would strand it if anything in between throws.
        """
        self.addCleanup(self._restore_local, name, getattr(frappe.local, name, _ABSENT))
        setattr(frappe.local, name, value)

    @staticmethod
    def _restore_local(name, original):
        """Absence is a value: werkzeug's ``Local`` raises for an unset name, so leaving
        ``None`` behind is not the same as never having stubbed."""
        if original is _ABSENT:
            try:
                delattr(frappe.local, name)
            except AttributeError:
                pass
        else:
            setattr(frappe.local, name, original)

    @staticmethod
    def _get_value(doctype, name, fieldname):
        if fieldname != "project":
            return None
        if doctype == "Salis Driver":
            return DRIVERS.get(name)
        if doctype == "Salis Vehicle":
            return VEHICLES.get(name)
        return None

    def scoped(self, projects=(PROJ_A,)):
        outer = patch.object(SP, "_is_unscoped", return_value=False)
        inner = patch.object(SP, "_allowed_projects", return_value=list(projects))
        outer.start()
        inner.start()
        self.addCleanup(inner.stop)
        self.addCleanup(outer.stop)
        self._stub_user_permissions(projects)

    def unscoped(self):
        outer = patch.object(SP, "_is_unscoped", return_value=True)
        outer.start()
        self.addCleanup(outer.stop)
        self._stub_user_permissions(())

    def _stub_user_permissions(self, projects):
        """Serve the ``applicable_for`` narrowing without a database.

        ``permission_scope.for_doctype`` re-reads frappe's own User Permission rows
        (permission_scope.py:104) to drop any value whose rows ALL name a different
        doctype. That read is real and is the point of the narrowing, so it is
        answered here with rows matching the scope this test already granted, each
        carrying no ``applicable_for`` — the row shape a plain project grant produces.
        """
        rows = {"Project": [{"doc": p, "applicable_for": None} for p in projects]}
        patcher = patch.object(
            frappe.permissions, "get_user_permissions", return_value=rows
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def own_driver(self, driver):
        """Point the User -> Employee -> Salis Driver chain at ``driver`` (or nothing).

        ``_driver_chain_has_permission`` calls ``get_driver_for_session_user`` on an
        UNSAVED row of a DocType carrying ``own="owner"`` — Vehicle Incident, Driver
        Attendance, Driver Suspension and Boarding Scan Log all do. That resolver reads
        User -> Employee -> Salis Driver from the database, which no test in this
        site-free module may reach, so it is stubbed at the same module-level point the
        sibling ``test_create_path_ownership_scope`` stubs it.
        """
        patcher = patch.object(SP, "get_driver_for_session_user", return_value=driver)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def doc(doctype, **kwargs):
        kwargs.setdefault("owner", "someone.else@example.com")
        return SimpleNamespace(doctype=doctype, **kwargs)


class TestTheCreatePathResolvesThroughTheVehicle(_ScopeCase):
    """Proof 1 — a create with the driver link still unfetched is decided on its merits."""

    def test_an_in_project_vehicle_allows_the_create(self):
        self.scoped()
        for doctype, field in FETCHED_DRIVER_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIsNone(
                    self.verdict(self.doc(doctype, **{field: None}, vehicle="VEH-A"), "create"),
                    f"{doctype}: a scoped supervisor cannot create on their own project",
                )

    def test_an_out_of_project_vehicle_still_refuses_the_create(self):
        """The easy mistake this guards: making create pass by making it pass for all."""
        self.scoped()
        for doctype, field in FETCHED_DRIVER_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIs(
                    self.verdict(self.doc(doctype, **{field: None}, vehicle="VEH-B"), "create"),
                    False,
                    f"{doctype}: a scoped supervisor created against another project",
                )

    def test_neither_link_resolving_still_fails_closed(self):
        self.scoped()
        for doctype, field in FETCHED_DRIVER_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIs(
                    self.verdict(self.doc(doctype, **{field: None}, vehicle=None), "create"),
                    False,
                )
                self.assertIs(
                    self.verdict(
                        self.doc(doctype, **{field: None}, vehicle="VEH-NONE"), "create"
                    ),
                    False,
                )

    def test_the_two_verdicts_are_not_the_same_verdict(self):
        self.scoped()
        _dt, field = FETCHED_DRIVER_DOCTYPES[0]
        allowed = self.verdict(
            self.doc("Vehicle Incident", **{field: None}, vehicle="VEH-A"), "create"
        )
        refused = self.verdict(
            self.doc("Vehicle Incident", **{field: None}, vehicle="VEH-B"), "create"
        )
        self.assertEqual((allowed, refused), (None, False))


class TestTheVehicleFallbackNeverLaundersAnOutOfScopeDriver(_ScopeCase):
    """Proof 2 — the fallback fires only when the driver chain resolved nothing."""

    def test_a_resolving_out_of_project_driver_is_denied_despite_an_in_project_vehicle(self):
        """A stored row's driver decides; an in-project vehicle must not rescue it."""
        self.scoped()
        for doctype, field in FETCHED_DRIVER_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIs(
                    self.verdict(self.doc(doctype, **{field: "DRV-B"}, vehicle="VEH-A"), "read"),
                    False,
                )

    def test_a_resolving_in_project_driver_still_defers(self):
        self.scoped()
        for doctype, field in FETCHED_DRIVER_DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIsNone(
                    self.verdict(self.doc(doctype, **{field: "DRV-A"}, vehicle="VEH-B"), "read")
                )

    def test_every_action_is_still_denied_out_of_project_not_just_create(self):
        self.scoped()
        for ptype in ("read", "write", "submit", "cancel", "delete"):
            with self.subTest(ptype=ptype):
                self.assertIs(
                    self.verdict(
                        self.doc("Vehicle Incident", driver=None, vehicle="VEH-B"), ptype
                    ),
                    False,
                )

    def test_a_scoped_user_holding_no_project_is_denied_through_the_vehicle_too(self):
        self.scoped(projects=())
        self.assertIs(
            self.verdict(
                self.doc("Vehicle Incident", driver=None, vehicle="VEH-A"), "create"
            ),
            False,
        )

    def test_oversight_defers(self):
        self.unscoped()
        self.assertIsNone(
            self.verdict(
                self.doc("Vehicle Incident", driver=None, vehicle="VEH-B"), "create"
            )
        )


class TestTheDriverOwnedDocTypesAreUnchanged(_ScopeCase):
    """Proof 3 — the ``own="owner"`` DocTypes carry no ``vehicle`` link, so nothing moved.

    Driver Attendance and Driver Suspension make ``driver`` mandatory and never fetch it, and
    Boarding Scan Log fetches it but grants the Driver an if_owner DocPerm that decides the
    create before the chain is consulted. The fallback must be a no-op for all three.
    """

    DOCTYPES = ["Driver Attendance", "Driver Suspension", "Boarding Scan Log"]

    def test_the_owner_still_decides_before_the_chain_on_a_stored_row(self):
        """These docs carry no ``__islocal``, so they are STORED rows. later made ownership insufficient on an UNSAVED row, which is a different
        document state, not a different action — the create-side counterpart of this
        assertion lives in ``test_create_path_ownership_scope``. Kept here as the stored
        half, which is what shows the vehicle fallback did not disturb these three.
        """
        self.scoped()
        for doctype in self.DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIsNone(
                    self.verdict(
                        SimpleNamespace(
                            doctype=doctype, driver=None, owner="supervisor@example.com"
                        ),
                        "read",
                    )
                )

    def test_a_non_owner_with_no_driver_still_fails_closed(self):
        self.scoped()
        for doctype in self.DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIs(self.verdict(self.doc(doctype, driver=None), "create"), False)

    def test_an_out_of_project_driver_is_still_denied(self):
        self.scoped()
        for doctype in self.DOCTYPES:
            with self.subTest(doctype=doctype):
                self.assertIs(self.verdict(self.doc(doctype, driver="DRV-B"), "read"), False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
