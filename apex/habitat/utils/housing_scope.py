# Copyright (c) 2026, afmcoltd
"""Which Active buildings the caller may see, derived once.

Three read endpoints — the Front Desk portfolio, its empty-state explainer, and the
Arrivals Desk building picker — each need the same answer. The derivation lives here,
not re-derived independently in each endpoint from the two ``permissions`` primitives,
so a change to what "in scope" means reaches all three.

``assert_party_in_scope`` absorbed the Arrivals Desk's per-doc scope gate: both the
Front Desk and the Arrivals Desk look up a party's PII by a client-supplied docname,
and both must re-apply the same building scope the list views get from
``permission_query_conditions`` (which cannot reach a direct ``get_value``). A second
copy of that gate anywhere else is one desk's PII leak rule drifting from the other's.
"""

from __future__ import annotations

from typing import NamedTuple

import frappe
from frappe import _

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.habitat import permissions
from apex.habitat.utils import occupancy


class BuildingScope(NamedTuple):
    """``filters`` selects the caller's visible Active buildings. It is ``None`` when
    the caller is confined to User-Permission buildings and holds none — an empty
    result for a very different reason than "no Active building exists"."""

    is_scoped: bool
    filters: dict | None


def active_building_scope(user) -> BuildingScope:
    """The caller's in-scope Active buildings. An unscoped oversight role sees every
    Active building; a building-scoped user sees only their User-Permission buildings."""
    if permissions._building_is_unscoped(user):
        return BuildingScope(False, {"status": "Active"})
    allowed = permissions._allowed_buildings(user)
    if not allowed:
        return BuildingScope(True, None)
    return BuildingScope(True, {"status": "Active", "name": ["in", allowed]})


def assert_party_in_scope(party_type, party) -> None:
    """Enforce per-doc BUILDING scope before any party PII / identity is returned.

    The desk lookups take a CLIENT-SUPPLIED docname. A type-level
    ``has_permission`` only proves the caller may read the doctype at all — it does
    NOT confine them to their own estate, so a scoped supervisor (or any low-role
    user with a type-level read) could otherwise harvest another building's worker
    identity, passport, and Iqama. This re-applies the same building scope the list
    views get via ``permission_query_conditions``. That hook runs inside
    ``DatabaseQuery`` (frappe/model/db_query.py), and the one thing it cannot do is
    reach a direct ``frappe.db.get_value`` — which is exactly the read below it, so
    the scope is asserted here or it is not asserted at all. Refusal raises
    ``frappe.PermissionError``, the class the framework itself uses.

    Unscoped oversight roles (HOUSING_UNSCOPED_ROLES) / Administrator pass through.
    Scoped-user rules per party type:

    * Temporary Worker — scoped on its own ``building`` field; a worker with no
      building (or one outside the caller's estate) is denied (a scoped user can
      never act on an estate-less party — mirrors permissions). The
      passport / Iqama leak (R1) lives here.
    * Employee — scoped on the building of its LIVE Accommodation Assignment. An
      employee actively housed in ANOTHER estate is denied (the real R2 leak). An
      employee with NO live assignment (a not-yet-housed arrival) is allowed, so
      the legitimate intake / check-in lookup the desk does before assigning a bed
      is never broken — that path exposes only name + photo, never PII.
    """
    user = frappe.session.user
    if permissions._building_is_unscoped(user):
        return

    allowed = set(permissions._allowed_buildings(user))

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
