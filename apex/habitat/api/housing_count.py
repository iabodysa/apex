# Copyright (c) 2026, AFMCO and contributors
"""Housing Inventory count API.

The testable backend for the count surface inside the housing portal
(``/housing#/count``): a mobile field surface where a supervisor picks a
building, sees its Housing Inventory lines grouped by room, and records a
physical count per line. It adds NO inventory model of its own — it reuses the
Housing Inventory DocType and its existing count fields. The controller is the
single deriver of ``quantity_variance`` (counted minus expected) and the stamper
of ``last_count_date``; this API never writes those derived fields.

Route trace, read off the built bundle: the only bundle referencing this module
is ``housing_portal``, which ``www/housing.html`` loads. The older standalone
``/housing-count`` route is now a redirect marker whose controller 301s to
``/housing#/count``, so it hosts no surface of its own.

Endpoints:

- :func:`get_inventory_for_building` returns the inventory lines for a building
  (optionally a single room), permission-checked so the caller's building scope
  applies. Read-only.
- :func:`submit_counts` records a count per submitted line via ``doc.save()`` so
  the Housing Inventory controller derives ``quantity_variance`` and stamps
  ``last_count_date``. Each row is wrapped in its own savepoint, so one bad line
  never rolls back the rest.

Permission model: NO ``ignore_permissions`` anywhere. The reads run through the
permission filter (``housing_inventory_query`` building scope), and each write is
gated by ``frappe.has_permission("Housing Inventory", "write", throw=True)`` plus
the per-doc ``building_scoped_has_permission`` check Frappe applies on save — so a
supervisor scoped to building A can neither read nor write building B's items.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

# [#m8nh8w]
_ITEM_FIELDS = [
    "name",
    "item_name",
    "item_category",
    "uom",
    "room",
    "expected_quantity",
    "counted_quantity",
    "quantity_variance",
    "condition",
    "status",
    "notes",
    "last_count_date",
]

# [#8ip76x]
_WRITABLE = ("counted_quantity", "condition", "notes")


def _condition_options():
    """Return the Housing Inventory ``condition`` Select option list.

    Read from the DocMeta so the portal's condition picker can never drift from
    the DocType's option set (server-driven enum display).
    """
    df = frappe.get_meta("Housing Inventory").get_field("condition")
    options = (df.options or "") if df else ""
    return [o for o in options.split("\n") if o]


@frappe.whitelist()
def get_inventory_for_building(building, room=None):
    """Return the Housing Inventory lines for a building (optionally one room).

    Permission-checked READ: the caller must have ``read`` on Housing Inventory,
    and the rows are fetched WITHOUT ``ignore_permissions`` so the building-scope
    ``permission_query_conditions`` confines a scoped supervisor to their own
    estate's items. A caller scoped off this building gets an empty list.

    Args:
        building: Accommodation Building docname (the count scope).
        room: optional Accommodation Room docname to narrow the list.

    Returns:
        ``{"building", "items": [...], "conditions": [...]}`` — each item carries
        the render fields in :data:`_ITEM_FIELDS` plus ``room_label`` (the room
        number for grouping), and ``conditions`` is the DocType's condition option
        set for the per-line picker.
    """
    frappe.has_permission("Housing Inventory", "read", throw=True)
    if not building:
        frappe.throw(_("A building is required to load the inventory."))

    filters = {"building": building}
    if room:
        filters["room"] = room

    # [#le8fuk]
    items = frappe.get_list(
        "Housing Inventory",
        filters=filters,
        fields=_ITEM_FIELDS,
        order_by="room asc, item_name asc",
        limit_page_length=0,
    )

    # [#80tm7s]
    room_names = sorted({it.room for it in items if it.room})
    labels = {}
    if room_names:
        for r in frappe.get_all(
            "Room",
            filters={"name": ["in", room_names]},
            fields=["name", "room_number"],
        ):
            labels[r.name] = r.room_number or r.name
    for it in items:
        it["room_label"] = labels.get(it.room) if it.room else None

    return {
        "building": building,
        "items": items,
        "conditions": _condition_options(),
    }


@frappe.whitelist(methods=["POST"])
def submit_counts(building, lines):
    """Record a physical count per submitted Housing Inventory line.

    Each line stages ``counted_quantity`` (+ optional ``condition`` / ``notes``)
    onto its existing Housing Inventory row and ``doc.save()``-s it, so the
    controller's ``before_save`` derives ``quantity_variance`` and stamps
    ``last_count_date``. The derived ``quantity_variance`` is NEVER written here.

    Permission: ``frappe.has_permission("Housing Inventory", "write",
    throw=True)`` gates the call up-front; every ``doc.save()`` runs WITHOUT
    ``ignore_permissions``, so the per-doc ``building_scoped_has_permission`` check
    fires and a row outside the caller's building scope is rejected. The
    ``building`` argument is verified to match each row, so a caller cannot smuggle
    in an out-of-building item id.

    Each row is wrapped in its own DB savepoint: a failure on one line rolls back
    only that line and is recorded in ``errors`` while the rest still save — a
    bad single item never voids a whole field count.

    Args:
        building: Accommodation Building docname (the count scope; every line
            must belong to it).
        lines: JSON list (or already-parsed list) of
            ``{"name", "counted_quantity", "condition"?, "notes"?}``.

    Returns:
        ``{"ok", "saved", "failed", "rows": [...], "errors": [...]}`` — ``rows``
        carry the reloaded ``name`` / ``item_name`` / ``quantity_variance`` /
        ``last_count_date`` so the summary can show the server-derived variance.
    """
    frappe.has_permission("Housing Inventory", "write", throw=True)

    if not building:
        frappe.throw(_("A building is required to submit counts."))

    if isinstance(lines, str):
        # [#2o10dh]
        try:
            lines = json.loads(lines)
        except ValueError:
            frappe.throw(_("Counts must be valid JSON."))
    if not isinstance(lines, list):
        frappe.throw(_("Counts must be a list."))
    if not lines:
        frappe.throw(_("No count lines to submit."))

    saved_rows = []
    errors = []
    for line in lines:
        name = line.get("name")
        if not name:
            errors.append({"name": None, "error": _("A line is missing its item.")})
            continue

        savepoint = "housing_count_" + frappe.scrub(name)
        frappe.db.savepoint(savepoint)
        try:
            # [#qwhtu5]
            doc = frappe.get_doc("Housing Inventory", name)
            if doc.building != building:
                # [#1e8yav]
                frappe.throw(
                    _("Item {0} does not belong to this building.").format(name),
                    frappe.PermissionError,
                )

            # [#f2430u]
            if line.get("counted_quantity") is not None:
                doc.counted_quantity = frappe.utils.flt(line.get("counted_quantity"))
            if line.get("condition"):
                doc.condition = line.get("condition")
            if "notes" in line:
                doc.notes = line.get("notes")

            # [#eipi09]
            doc.save()
        except Exception as e:
            frappe.db.rollback(save_point=savepoint)
            errors.append({"name": name, "error": str(e)})
            continue
        else:
            frappe.db.release_savepoint(savepoint)
            doc.reload()
            saved_rows.append(
                {
                    "name": doc.name,
                    "item_name": doc.item_name,
                    "quantity_variance": doc.quantity_variance,
                    "last_count_date": doc.last_count_date,
                }
            )

    return {
        "ok": not errors,
        "saved": len(saved_rows),
        "failed": len(errors),
        "rows": saved_rows,
        "errors": errors,
    }
