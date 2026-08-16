# Copyright (c) 2026, afmcoltd
"""Which Active buildings the caller may see, derived once.

Three read endpoints — the Front Desk portfolio, its empty-state explainer, and the
Arrivals Desk building picker — each need the same answer. The derivation lives here,
not re-derived independently in each endpoint from the two ``permissions`` primitives,
so a change to what "in scope" means reaches all three.
"""

from __future__ import annotations

from typing import NamedTuple

from apex.habitat import permissions


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
