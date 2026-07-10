# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Movement controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from apex.habitat.asset_movement_engine import (
    post_asset_movement,
    reverse_asset_movement,
)


class FacilityAssetMovement(Document):
    pass


def validate(doc, method=None):
    # [#mkyjak]
    _reconcile_origin(doc)
    _populate_company_fields(doc)
    _detect_intercompany(doc)

    if doc.from_building == doc.to_building and doc.from_room == doc.to_room:
        frappe.throw(_("From and To location must differ for a Facility Asset Movement."))

    if doc.is_intercompany:
        _validate_intercompany_gates(doc)


def on_submit(doc, method=None):
    """Actually move the asset: snapshot its current location into previous_*, set the
    new building/location from this movement, and bump the movement audit fields.

    The previous code wrote ``current_building``/``current_room``, which do NOT exist
    on Facility Asset (its fields are ``building``/``location_in_building``), so the
    guarded ``updates`` dict stayed empty — every movement was a silent no-op and the
    audit fields (previous_*/movement_count/last_movement_date) never populated."""
    # Post the immutable from->to history row first; the in-place update below only
    # tracks the current location, not the move history.
    post_asset_movement(doc)
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building", "movement_count"],
        as_dict=True,
    )
    if not asset:
        return
    # location_in_building is free-text Data; to_room is a Link whose docname IS the
    # Accommodation Room's room_number, so the stored value stays human-readable AND
    # round-trips with _reconcile_origin (which only matches a value that is a Room).
    frappe.db.set_value("Facility Asset", doc.facility_asset, {
        "previous_building": asset.building,
        "previous_location_in_building": asset.location_in_building,
        "building": doc.to_building,
        "location_in_building": doc.to_room,
        "movement_count": (asset.movement_count or 0) + 1,
        "last_movement_date": today(),
    })


def on_cancel(doc, method=None):
    """Revert the asset to where it came from when a submitted movement is cancelled."""
    # Reverse the ledger (negated mirror row, not a delete) so the history stays
    # auditable; runs even if the asset row was deleted after the move.
    reverse_asset_movement(doc.doctype, doc.name)
    if not frappe.db.exists("Facility Asset", doc.facility_asset):
        return
    count = frappe.db.get_value("Facility Asset", doc.facility_asset, "movement_count") or 0
    frappe.db.set_value("Facility Asset", doc.facility_asset, {
        "building": doc.from_building,
        "location_in_building": doc.from_room,
        "movement_count": max(0, count - 1),
    })


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Facility Asset Movement."))


def _reconcile_origin(doc):
    """The origin is hand-entered and can drift from where the asset actually is.
    Default blank from_* from the asset's recorded location, and reject a hand-entered
    origin that contradicts it so the move can't start from a phantom location."""
    if not doc.facility_asset:
        return
    asset = frappe.db.get_value(
        "Facility Asset",
        doc.facility_asset,
        ["building", "location_in_building"],
        as_dict=True,
    )
    if not asset:
        return
    if not doc.from_building:
        doc.from_building = asset.building
    elif asset.building and doc.from_building != asset.building:
        frappe.throw(
            _("From Building does not match the asset's current location ({0}).").format(asset.building)
        )
    # from_room is a Link(Accommodation Room); the asset stores its place in the
    # free-text Data field location_in_building. Reconcile only against a value that
    # is actually a Room docname (prior moves write the room there) — a descriptive
    # free-text location ("Laundry Room") is not a Room and must not false-throw.
    asset_room = asset.location_in_building
    if asset_room and not frappe.db.exists("Room", asset_room):
        asset_room = None
    if not doc.from_room:
        doc.from_room = asset_room
    elif asset_room and doc.from_room != asset_room:
        frappe.throw(
            _("From Room does not match the asset's current location ({0}).").format(asset_room)
        )


def _populate_company_fields(doc):
    if doc.from_building and not doc.from_company:
        doc.from_company = frappe.db.get_value("Building", doc.from_building, "company") or None
    if doc.to_building and not doc.to_company:
        doc.to_company = frappe.db.get_value("Building", doc.to_building, "company") or None


def _detect_intercompany(doc):
    if doc.from_company and doc.to_company and doc.from_company != doc.to_company:
        doc.is_intercompany = 1
    else:
        doc.is_intercompany = 0


def _validate_intercompany_gates(doc):
    """Block intercompany submissions without release approval and receiving confirmation."""
    if not doc.release_approved_by:
        frappe.throw(_("Release Approved By is required for intercompany asset movement."))
    if not doc.receiving_confirmed_by:
        frappe.throw(_("Receiving Confirmed By is required for intercompany asset movement."))
    if doc.movement_category == "Intercompany Permanent" and not doc.accounting_acknowledged:
        frappe.throw(
            _("Accounting Acknowledged is required before submitting a permanent intercompany transfer.")
        )
