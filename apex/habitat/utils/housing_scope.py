# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from typing import NamedTuple

import frappe
from frappe import _

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.habitat import permissions
from apex.habitat.utils import occupancy


class BuildingScope(NamedTuple):

    is_scoped: bool
    filters: dict | None


def active_building_scope(user) -> BuildingScope:
    if permissions._building_is_unscoped(user):
        return BuildingScope(False, {"status": "Active"})
    allowed = permissions.allowed_buildings(user)
    if not allowed:
        return BuildingScope(True, None)
    return BuildingScope(True, {"status": "Active", "name": ["in", allowed]})


def assert_party_in_scope(party_type, party) -> None:
    user = frappe.session.user
    if permissions._building_is_unscoped(user):
        return

    allowed = set(permissions.allowed_buildings(user))

    if party_type == PARTY_TEMPORARY_WORKER:
        building = frappe.db.get_value("Temporary Worker", party, "building")
        if not building or building not in allowed:
            raise frappe.PermissionError(
                _("You are not permitted to access this worker's record.")
            )
        return

    if party_type == PARTY_EMPLOYEE:
        building = frappe.db.get_value(
            "Housing Assignment",
            occupancy.active_assignment_filters(party_type=PARTY_EMPLOYEE, party=party),
            "building",
        )
        if building and building not in allowed:
            raise frappe.PermissionError(
                _("You are not permitted to access this worker's record.")
            )
        return
