# Copyright (c) 2026, afmcoltd
"""Transfer Board API.

A thin presentation + orchestration layer over the existing Room Bed Transfer
controller. This module adds NO bed-status, locking, or ledger logic of its own.

The page reuses the read-only ``front_desk.get_building_grid`` reader (one bulk,
N+1-free call per pane) to render two side-by-side building bed grids. The only
write is :func:`transfer_occupant`, which resolves the move SERVER-SIDE and then
builds + submits a real Room Bed Transfer so the existing controller runs:

- ``validate()`` rejects an Out-of-Service or already-Occupied target, checks
  bed/room/building consistency, and REJECTS A CROSS-BUILDING MOVE;
- ``on_submit()`` flips the bed statuses, re-points the active assignment's
  ``bed`` / ``room`` / ``building`` in place (no new assignment, no checkout, no
  ledger entry), and recalculates the room/building occupancy counters.

The cross-building rule used to be raised HERE as well. It is not any more: this
page is one caller among several, so a copy of the rule in the page left the Desk
form, ``frappe.client`` REST and Data Import free to bypass it. The rule now lives
only in the controller, where every path meets it, and this page inherits it.

Concurrency: the integrity guarantee lives in the controller, not in this page.
The Room Bed Transfer controller is being hardened with a ``SELECT ... FOR
UPDATE`` row lock on the target bed; it holds that lock for the duration of the
move. If two operators drop onto the SAME empty target at once, the controller
serializes them — the loser hits "Target bed is already occupied" and throws.
The page never mutates the DOM optimistically: after every write it re-fetches
BOTH panes, so a losing operator immediately sees the corrected state.

Active-occupancy semantics: ``docstatus == 1`` AND ``check_out_date`` is not set.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today


@frappe.whitelist(methods=["POST"])
def transfer_occupant(source_bed, target_bed, transfer_date=None, reason=None):
    """Move the active occupant of ``source_bed`` onto an empty ``target_bed``.

    The move is performed by building and submitting a Room Bed Transfer (an
    in-place bed re-pointing) — never a manual bed-status flip. Everything is
    derived SERVER-SIDE and never trusted from the client:

    1. Resolve the single active Accommodation Assignment on ``source_bed``
       (``docstatus == 1`` AND ``check_out_date`` is not set). Throw if none.
    2. Resolve the target room from ``target_bed``.
    3. Build ``{doctype: "Room Bed Transfer", assignment, to_room, to_bed,
       transfer_date or today, reason}``. ``from_bed`` and ``employee`` are
       ``fetch_from`` the assignment on the DocType, so they are NOT set here.
    4. ``insert()`` + ``submit()`` so the Room Bed Transfer controller runs
       natively — including its cross-building rejection, the SELECT ... FOR
       UPDATE target-bed lock, the bed status flips, the in-place assignment
       re-point, and the occupancy recalculation.

    This method adds NO bed-status, locking, or ledger logic of its own.

    Permission: caller must have ``create`` AND ``submit`` on Room Bed Transfer
    (checked explicitly below; defense in depth over the role grant).

    Args:
        source_bed: Accommodation Bed docname holding the active occupant.
        target_bed: empty Accommodation Bed docname to move the occupant onto.
        transfer_date: optional ISO date string; defaults to today.
        reason: optional free-text reason carried onto the transfer.

    Returns:
        dict: ``{"transfer": <docname>, "source_bed": <bed>, "target_bed": <bed>}``.
    """
    frappe.has_permission("Room Bed Transfer", "create", throw=True)
    frappe.has_permission("Room Bed Transfer", "submit", throw=True)

    if not source_bed or not target_bed:
        frappe.throw(_("Both a source bed and a target bed are required."))
    if source_bed == target_bed:
        frappe.throw(_("Source and target beds must be different."))

    assignment = frappe.db.get_value(
        "Housing Assignment",
        {"bed": source_bed, "docstatus": 1, "check_out_date": ["is", "not set"]},
        "name",
    )
    if not assignment:
        frappe.throw(_("Source bed has no active resident to transfer."))

    target_room, target_building = frappe.db.get_value(
        "Bed", target_bed, ["room", "building"]
    )
    if not target_room or not target_building:
        frappe.throw(_("Target bed {0} is not linked to a room and building.").format(target_bed))

    doc = frappe.get_doc(
        {
            "doctype": "Room Bed Transfer",
            "assignment": assignment,
            "to_room": target_room,
            "to_bed": target_bed,
            "transfer_date": transfer_date or today(),
            "reason": reason,
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"transfer": doc.name, "source_bed": source_bed, "target_bed": target_bed}
