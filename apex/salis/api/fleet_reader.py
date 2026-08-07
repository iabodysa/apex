# Copyright (c) 2026, afmcoltd
"""Shared fleet-reader service for the two Salis fleet surfaces.

Both fleet views answer the same underlying question — "what is every permitted
vehicle's state and driver right now?" — and so must resolve scope and fetch the
base vehicle set IDENTICALLY, even though they then shape the result for
different surfaces:

  * :mod:`apex.salis.api.fleet_os` — the ``/fleet-os`` supervisor SPA, which
    needs the supervisor-design shape (per-vehicle ``current_driver``/
    ``history``/``damages``/``accidents``/``stolen_info``);
  * :mod:`apex.salis.api.operations_control` — the ``operations-control``
    desk Page board, which needs the card/table shape (``current_driver_name``/
    ``open_incidents`` + a status ``summary``).

Route trace for the SPA half, read off the built bundles rather than assumed:
``www/fleet-os.html`` loads ``/assets/apex/fleet_os_portal/assets/index.js``, and
that bundle is the only one referencing ``apex.salis.api.fleet_os``, which imports
this module. The ``/fleet`` bundle (``fleet_portal``) references
``apex.salis.api.fleet_employee`` alone, so nothing here reaches ``/fleet``. The
desk half has no bundle at all — ``operations-control`` is a Desk Page.

This module owns the SHARED half: the project-scope resolution and the bounded,
N+1-free base ``Salis Vehicle`` query, plus the driver-name enrichment both
readers do. The two readers keep their own surface SHAPE and their own incident
shaping (legitimately different per surface). Scope itself already came from the
one canonical resolver (``dispatch_board._permitted_projects``); this keeps the
base query and the driver lookup from drifting between the two surfaces too.
"""

from __future__ import annotations

import frappe

from apex.salis.api.dispatch_board import _permitted_projects


def scope_filter():
    """Resolve project scope into a ready-to-use Salis Vehicle filter.

    Returns ``(unscoped, projects, filters)``:

      * ``unscoped`` — True for oversight roles that see every project;
      * ``projects`` — the permitted Project names (``None`` when unscoped);
      * ``filters`` — the project filter dict to pass to ``frappe.get_all`` on
        ``Salis Vehicle``: ``{}`` when unscoped, ``{"project": ["in", projects]}``
        when scoped to one or more projects, and ``None`` when the user is scoped
        but holds NO project. A ``None`` filter is the access-gap signal: the
        caller must short-circuit to an empty result (it must NOT fall through to
        an unfiltered query).
    """
    unscoped, projects = _permitted_projects()
    if unscoped:
        return True, None, {}
    if not projects:
        return False, projects, None
    return False, projects, {"project": ["in", projects]}


def scoped_vehicles(fields, base_filters, extra_filters=None, or_filters=None, order_by="plate_number asc"):
    """Fetch the scoped vehicle rows in one bounded query (no N+1, no raw SQL).

    ``base_filters`` is the dict returned by :func:`scope_filter` (already
    resolved to the project scope); callers pass it straight through. Any
    ``extra_filters`` (status / rental_office / a caller-narrowed project) are
    merged on top. ``fields`` is the caller's surface-specific column set, so the
    shared query never over-fetches.
    """
    filters = dict(base_filters or {})
    if extra_filters:
        filters.update(extra_filters)
    return frappe.get_all(
        "Salis Vehicle",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by=order_by,
        limit_page_length=0,
    )


def driver_names(vehicle_rows):
    """Map ``current_driver`` -> Salis Driver ``full_name`` for the given rows.

    One bounded ``get_all`` over the distinct current drivers on the board; an
    empty dict when no vehicle has a current driver. Shared so both surfaces
    resolve the driver label the same way.
    """
    ids = list({v.get("current_driver") for v in vehicle_rows if v.get("current_driver")})
    if not ids:
        return {}
    return {
        d.name: d.full_name
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", ids]},
            fields=["name", "full_name"],
        )
    }
