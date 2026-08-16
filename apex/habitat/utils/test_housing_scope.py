# Copyright (c) 2026, afmcoltd
"""Contract test for ``active_building_scope``.

An unscoped oversight role sees every Active building (``is_scoped=False``,
``filters={"status": "Active"}``). A building-scoped user with a granted
building is confined to it. A building-scoped user holding NO building gets an
EMPTY allowance (``is_scoped=True``, ``filters=None``) — a run as Administrator
proves nothing here, since Administrator is always unscoped, so every case below
switches session user via ``as_user``.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.utils.housing_scope import BuildingScope, active_building_scope
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_building, make_company


class TestActiveBuildingScope(FrappeTestCase):
    def test_unscoped_oversight_role_sees_every_active_building(self):
        email = _user("a564-hs-manager@example.com", "Accommodation Manager")
        with as_user(email):
            scope = active_building_scope(email)
        self.assertEqual(scope, BuildingScope(False, {"status": "Active"}))

    def test_scoped_user_with_granted_building_is_confined_to_it(self):
        make_company()
        building = make_building(name="A564 Housing Scope Building")
        email = _user("a564-hs-supervisor@example.com", "Resident Supervisor")
        up = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Building",
                "for_value": building.name,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "User Permission", up.name, force=True, ignore_permissions=True)

        with as_user(email):
            scope = active_building_scope(email)

        self.assertEqual(
            scope,
            BuildingScope(True, {"status": "Active", "name": ["in", [building.name]]}),
        )

    def test_scoped_user_with_no_granted_building_gets_empty_allowance(self):
        email = _user("a564-hs-noscope@example.com", "Resident Supervisor")
        with as_user(email):
            scope = active_building_scope(email)
        self.assertEqual(scope, BuildingScope(True, None))
